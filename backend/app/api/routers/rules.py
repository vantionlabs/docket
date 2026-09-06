"""Rules: the explicit gate of rail 3 (spec sections 9 and 15).

The model proposes an outcome. A rule decides whether a human sees it.
Nothing here lets a model widen its own authority: a rule is written by a
person, stored per org, and starts with `auto_approve` off.

Only an owner may change a rule. Changing a rule changes what executes
without review, so it is not something a reviewer does between approvals.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import NOT_FOUND, UNAUTHORIZED, RuleIn, RuleOut
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import Role, Rule

router = APIRouter(prefix="/rules", tags=["rules"], responses=UNAUTHORIZED)


def _require_owner(user: CurrentUser) -> None:
    if user.role is not Role.owner:
        raise HTTPException(
            403,
            "Only an owner may change rules. A rule decides what executes "
            "without review, so it is not a reviewer's call.",
        )


def _require_rule(db: Session, rule_id: uuid.UUID, org_id: uuid.UUID) -> Rule:
    rule = db.get(Rule, rule_id)
    if rule is None or rule.org_id != org_id:
        raise HTTPException(404, "Rule not found")
    return rule


@router.get("", response_model=list[RuleOut], summary="Rules for this org")
def list_rules(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Rule]:
    return list(
        db.scalars(
            select(Rule).where(Rule.org_id == user.org_id).order_by(Rule.created_at.desc())
        )
    )


@router.post(
    "",
    response_model=RuleOut,
    status_code=201,
    summary="Create a rule",
    description=(
        "`auto_approve` defaults to false, and it should stay false until "
        "the eval set says the rule is safe (spec section 13). A rule with "
        "`auto_approve` off is still useful: it names the approver."
    ),
    responses={403: {"description": "Only an owner may change rules"}},
)
def create_rule(
    body: RuleIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Rule:
    _require_owner(user)
    rule = Rule(
        org_id=user.org_id,
        name=body.name,
        schema_name=body.schema_name,
        conditions=body.conditions.model_dump(mode="json"),
        auto_approve=body.auto_approve,
        active=body.active,
    )
    db.add(rule)
    db.commit()
    return rule


@router.put(
    "/{rule_id}",
    response_model=RuleOut,
    summary="Replace a rule",
    responses={**NOT_FOUND, 403: {"description": "Only an owner may change rules"}},
)
def update_rule(
    rule_id: uuid.UUID,
    body: RuleIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Rule:
    _require_owner(user)
    rule = _require_rule(db, rule_id, user.org_id)
    rule.name = body.name
    rule.schema_name = body.schema_name
    rule.conditions = body.conditions.model_dump(mode="json")
    rule.auto_approve = body.auto_approve
    rule.active = body.active
    db.commit()
    return rule


@router.delete(
    "/{rule_id}",
    status_code=204,
    summary="Delete a rule",
    responses={**NOT_FOUND, 403: {"description": "Only an owner may change rules"}},
)
def delete_rule(
    rule_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_owner(user)
    db.delete(_require_rule(db, rule_id, user.org_id))
    db.commit()
