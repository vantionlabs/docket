"""Org resolution: turning a user into a tenant with authority.

Spec section 11. The template's explicit non-goal, and the single biggest
lift here, because nobody buys an approval queue that cannot tell two
companies apart.

The scoping happens at the dependency seam, not at each call site. Every
route already depends on `get_current_user`; that contract now carries the
active org and what the member may do in it, so a route that forgets to
filter is a route that cannot compile rather than one that leaks.

**Authority.** Role says whether you may approve at all: owner and reviewer
may, viewer may not. `approval_limit` optionally narrows that by amount. A
NULL limit means unlimited within your role, which is the natural reading
of "a role plus a threshold": the threshold is optional narrowing, not a
missing requirement. It is set explicitly when a member is added, so an
unlimited reviewer is somebody's decision rather than an oversight.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Membership, Organization, Role
from app.logging import get_logger

log = get_logger(__name__)

# Roles that may act on a decision at all.
APPROVERS = frozenset({Role.owner, Role.reviewer})


def ensure_personal_org(db: Session, user_id: uuid.UUID, email: str) -> Membership:
    """The org a user lands in when nobody has invited them anywhere.

    A single-tenant-looking experience on multi-tenant foundations: the
    user gets their own org and owns it, and inviting somebody else later
    is a membership row rather than a migration.
    """
    existing = db.scalar(select(Membership).where(Membership.user_id == user_id))
    if existing is not None:
        return existing

    org = Organization(name=_default_org_name(email))
    db.add(org)
    db.flush()

    membership = Membership(
        org_id=org.id,
        user_id=user_id,
        role=Role.owner,
        approval_limit=None,  # unlimited: it is their own org
    )
    db.add(membership)
    db.commit()
    log.info("org.created", org_id=str(org.id), user_id=str(user_id))
    return membership


def _default_org_name(email: str) -> str:
    """Name the org after the email domain, falling back to the local part.

    A personal gmail becomes "Alex", a company address becomes "Northwind".
    Neither is important enough to ask about at sign-up, and both are
    editable later.
    """
    local, _, domain = email.partition("@")
    generic = {"gmail.com", "outlook.com", "hotmail.com", "icloud.com", "proton.me"}
    if domain and domain.lower() not in generic:
        return domain.split(".")[0].replace("-", " ").title()
    return (local or "Personal").replace(".", " ").replace("-", " ").title()


def active_membership(db: Session, user_id: uuid.UUID, email: str) -> Membership:
    """The membership a request acts under.

    One org per user for now. When a user can belong to several, this is
    the one function that has to learn about an org switcher, and nothing
    above it changes.
    """
    membership = db.scalar(
        select(Membership).where(Membership.user_id == user_id).order_by(Membership.created_at)
    )
    if membership is None:
        membership = ensure_personal_org(db, user_id, email)
    return membership


def may_approve(role: Role, approval_limit: Decimal | None, amount: Decimal | None) -> bool:
    """Whether this member may approve a decision worth `amount`.

    An unknown amount is not approvable under a limit. A member with a
    ceiling has it for a reason, and "we could not read the total" is not
    evidence that the total is under it.
    """
    if role not in APPROVERS:
        return False
    if approval_limit is None:
        return True
    if amount is None:
        return False
    return amount <= approval_limit
