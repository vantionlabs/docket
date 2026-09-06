"""The app-facing auth seam.

Every route depends on `get_current_user`, which returns the minimal
`CurrentUser` the rest of the app needs. It accepts EITHER:

  - the httpOnly session cookie (browsers), or
  - an `X-API-Key: sk_...` key (service-to-service, headless, widgets).

This indirection is deliberate: to escalate a project to an external identity
provider (Keycloak/Authentik OIDC, WorkOS, ...), reimplement ONLY this
function to verify that provider's token. See docs/setup-auth.md.

Docket extends the contract with the active org and the member's authority
in it (spec section 11). Scoping lives here rather than at each call site,
so a route gets its tenant by depending on the seam it already depends on
and cannot forget to.
"""

import uuid
from decimal import Decimal

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.api_keys import resolve_api_key
from app.auth.backend import fastapi_users
from app.auth.orgs import active_membership, may_approve
from app.db.engine import get_db
from app.db.models import Role, User

# `optional=True` → returns None instead of 401 when no cookie, so we can fall
# through to the API-key path.
current_user_optional = fastapi_users.current_user(active=True, optional=True)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: str
    org_id: uuid.UUID
    role: Role
    approval_limit: Decimal | None = None
    """The most this member may approve alone. None means unlimited within
    their role, set deliberately when the member was added."""

    def may_approve(self, amount: Decimal | None) -> bool:
        return may_approve(self.role, self.approval_limit, amount)


def _with_org(db: Session, user_id: uuid.UUID, email: str) -> CurrentUser:
    """Attach the active org and authority to an authenticated identity."""
    membership = active_membership(db, user_id, email)
    return CurrentUser(
        id=user_id,
        email=email,
        org_id=membership.org_id,
        role=membership.role,
        approval_limit=membership.approval_limit,
    )


def get_current_user(
    cookie_user: User | None = Depends(current_user_optional),
    api_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if cookie_user is not None:
        return _with_org(db, cookie_user.id, cookie_user.email)

    if api_key:
        user_id = resolve_api_key(db, api_key)
        if user_id is not None:
            row = db.get(User, user_id)
            if row is not None:
                return _with_org(db, row.id, row.email)

    raise HTTPException(status_code=401, detail="Not authenticated")
