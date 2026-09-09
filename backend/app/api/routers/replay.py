"""Counterfactual replay: asking the history about a rule it never ran.

The endpoint a client uses before changing a threshold, and the reason the
decision row stores what the model proposed as well as what the system did.
Both routes are read-only — nothing here writes a decision, a rule or an
event — which is why they are POSTs only because the question has a body.

Owner-only, matching `rules`. The answer is what an owner uses to decide
whether to widen a gate, and it names the suppliers and amounts on the far
side of it.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    NOT_FOUND,
    UNAUTHORIZED,
    ExposureOut,
    FlipOut,
    ReplayOut,
    ReplayRequest,
)
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import Collection, DocumentChunk, Role
from app.decisions.replay import exposure, replay, rule_from_conditions

router = APIRouter(prefix="/replay", tags=["replay"], responses=UNAUTHORIZED)


def _require_owner(user: CurrentUser) -> None:
    if user.role is not Role.owner:
        raise HTTPException(
            403,
            "Only an owner may replay the decision history against a proposed "
            "rule. The answer names the amounts and suppliers a wider gate "
            "would let through.",
        )


def _flip(flip) -> FlipOut:
    return FlipOut(
        decision_id=flip.decision_id,
        document_id=flip.document_id,
        filename=flip.filename,
        was=flip.was,
        would_be=flip.would_be,
        amount=flip.amount,
        supplier=flip.supplier,
        reason=flip.reason,
    )


@router.post(
    "",
    response_model=ReplayOut,
    summary="What a proposed rule would have done",
    description=(
        "Re-runs the rails over every decision this org has made, under a rule "
        "that does not exist yet, and reports which decisions land somewhere "
        "else.\n\n"
        "Exact, and free: rail 3 is deterministic and every input it reads was "
        "stored at decision time, so no model is called. The rails can only "
        "ever move a decision toward a human, so a wider limit cannot loosen "
        "a grounding failure or an unverified field — only the threshold "
        "itself moves.\n\n"
        "`unreplayable` counts decisions made before the proposal was recorded. "
        "They are excluded rather than assumed."
    ),
)
def replay_rule(
    request: ReplayRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReplayOut:
    _require_owner(user)

    rule = None
    if request.conditions is not None:
        rule = rule_from_conditions(
            request.name, request.conditions.model_dump(mode="json"), active=True
        )

    report = replay(db, user.org_id, rule, request.schema_name, limit=request.limit)
    return ReplayOut(
        considered=report.considered,
        unreplayable=report.unreplayable,
        auto_approved_before=report.auto_approved_before,
        auto_approved_after=report.auto_approved_after,
        automation_rate_before=report.automation_rate_before,
        automation_rate_after=report.automation_rate_after,
        value_newly_automatic=report.value_newly_automatic,
        newly_automatic=[_flip(f) for f in report.newly_automatic],
        newly_reviewed=[_flip(f) for f in report.newly_reviewed],
    )


@router.get(
    "/clauses/{chunk_id}",
    response_model=ExposureOut,
    responses=NOT_FOUND,
    summary="What a clause is holding up",
    description=(
        "Every past decision that cited this clause, and what they were worth. "
        "The honest half of a policy-change question: editing a clause changes "
        "what the model would propose, and that cannot be known without asking "
        "it again — so this reports the blast radius exactly and claims nothing "
        "about the outcomes."
    ),
)
def clause_exposure(
    chunk_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExposureOut:
    _require_owner(user)

    chunk = db.get(DocumentChunk, chunk_id)
    if chunk is None or chunk.org_id != user.org_id or chunk.collection is not Collection.policy:
        raise HTTPException(404, "Policy clause not found")

    found = exposure(db, user.org_id, chunk_id)
    return ExposureOut(
        clause_ref=found.clause_ref or chunk.content[:80],
        decisions=found.decisions,
        amount=found.amount,
        outcomes=found.outcomes,
        sample=[decision_id for decision_id, _ in found.sample],
    )
