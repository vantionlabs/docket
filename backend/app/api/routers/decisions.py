"""The review queue and the approval endpoints (spec sections 6 and 15).

`POST /decisions/{id}/approve` is the human half of the split. It emits the
same `decision.execute` event the router emits for an auto-approved
decision, so there is one execution path and the approval is just another
way to reach it.

Approving is idempotent at the event layer: the key is derived from the
decision and the action, so a reviewer who double-clicks gets one event and
one execution.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import (
    NOT_FOUND,
    UNAUTHORIZED,
    ApprovalResponse,
    ApproveRequest,
    DecisionDetailOut,
    DecisionOut,
    ExtractedFieldOut,
    RejectRequest,
)
from app.auth.access import require_decision_access
from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.orgs import APPROVERS
from app.db.engine import get_db
from app.db.models import Decision, DecisionStatus, Extraction, SourceDocument
from app.decisions.approval import emit_execute
from app.decisions.models import Outcome
from app.extraction.schemas import field_order

router = APIRouter(prefix="/decisions", tags=["decisions"], responses=UNAUTHORIZED)

# A reviewer may only overrule toward an outcome a human can act on.
# `auto_approve` is not among them: rail 3 says a rule authorises automatic
# execution, and a reviewer approving by hand is not an automatic execution.
OVERRIDABLE = {Outcome.route_for_approval, Outcome.reject, Outcome.needs_human}


@router.get(
    "",
    response_model=list[DecisionOut],
    summary="The review queue",
    description=(
        "Decisions for the current user, oldest first so nothing ages out of "
        "sight. Filter by `status` to get the pending queue."
    ),
)
def list_decisions(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: DecisionStatus | None = Query(default=None, description="Filter by status."),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Decision]:
    stmt = (
        select(Decision)
        .where(Decision.org_id == user.org_id)
        .options(selectinload(Decision.citations))
        .order_by(Decision.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(Decision.status == status)
    return _summarize(db, list(db.scalars(stmt)))


def _summarize(db: Session, decisions: list[Decision]) -> list[DecisionOut]:
    """Attach the filename, supplier and amount to each queue row.

    A queue row has to say what the case is before it says why it stalled.
    "Grounding failed" is true and useless; "Fabrikam, EUR 12,196.80" is
    what a reviewer recognises. One batched lookup, not one per row.
    """
    if not decisions:
        return []

    documents = {
        row.id: row.filename
        for row in db.execute(
            select(SourceDocument.id, SourceDocument.filename).where(
                SourceDocument.id.in_({d.document_id for d in decisions})
            )
        )
    }
    extractions = {
        row.id: row.fields
        for row in db.execute(
            select(Extraction.id, Extraction.fields).where(
                Extraction.id.in_({d.extraction_id for d in decisions if d.extraction_id})
            )
        )
    }

    def value(fields: dict | None, name: str) -> str | None:
        field = (fields or {}).get(name)
        if isinstance(field, dict) and field.get("value") is not None:
            return str(field["value"])
        return None

    out: list[DecisionOut] = []
    for decision in decisions:
        fields = extractions.get(decision.extraction_id) or {}
        summary = DecisionOut.model_validate(decision, from_attributes=True)
        summary.filename = documents.get(decision.document_id, "")
        summary.supplier = value(fields, "supplier")
        summary.amount = value(fields, "total_incl_vat")
        summary.currency = value(fields, "currency")
        out.append(summary)
    return out


@router.get(
    "/stats",
    summary="Queue header numbers (spec section 15)",
    description=(
        "Pending, decided today, auto-approved share, and override rate. The "
        "last two are the numbers that prove the thing works."
    ),
)
def decision_stats(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    def count(*where) -> int:
        return db.scalar(
            select(func.count()).select_from(Decision).where(Decision.org_id == user.org_id, *where)
        ) or 0

    total = count()
    reviewed = count(Decision.reviewed_at.is_not(None))
    return {
        "pending": count(Decision.status == DecisionStatus.pending_review),
        "executed": count(Decision.status == DecisionStatus.executed),
        "total": total,
        # Counted on the outcome, which is what the label says. It used to
        # count rows with a `rule_id`, a fair proxy in real data and a wrong
        # one the moment anything else wrote to that column.
        "auto_approved": count(Decision.outcome == str(Outcome.auto_approve)),
        "overridden": count(Decision.override_outcome.is_not(None)),
        # Share of reviewed decisions where the human disagreed. Undefined
        # rather than zero when nobody has reviewed anything yet.
        "override_rate": (
            count(Decision.override_outcome.is_not(None)) / reviewed if reviewed else None
        ),
    }


@router.get(
    "/{decision_id}",
    response_model=DecisionDetailOut,
    summary="One decision, with its extracted fields and cited clauses",
    description=(
        "The demo screen's payload: the document, what was read off it with "
        "each value's source span, and the policy clauses that justified the "
        "outcome."
    ),
    responses=NOT_FOUND,
)
def get_decision(
    decision_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DecisionDetailOut:
    decision = require_decision_access(db, decision_id, user.org_id)
    extraction = (
        db.get(Extraction, decision.extraction_id)
        if decision.extraction_id is not None
        else None
    )

    unverified = set(extraction.unverified_fields if extraction else ())
    # Built from the same summary the queue rows use, so the header shows
    # the supplier and amount without a second way of deriving them.
    summary = _summarize(db, [decision])[0]
    return DecisionDetailOut(
        **summary.model_dump(),
        document_text=extraction.document_text if extraction else "",
        unverified_fields=sorted(unverified),
        arithmetic_ok=extraction.arithmetic_ok if extraction else True,
        arithmetic_failures=list(extraction.arithmetic_failures) if extraction else [],
        fields=_flatten_fields(
            extraction.fields if extraction else {},
            unverified,
            extraction.schema_name if extraction else "",
        ),
    )


def _flatten_fields(
    fields: dict, unverified: set[str], schema_name: str = ""
) -> list[ExtractedFieldOut]:
    """Turn the stored extraction into rows the detail screen can render.

    Walks nested models and lists the same way the verifier does, so a
    field's path here is the path that appears in `unverified_fields`.

    Ordered by the schema's own field order, because JSONB does not preserve
    key order and a reviewer scanning top-down should meet the supplier and
    the total before fifteen line-item components.
    """
    out: list[ExtractedFieldOut] = []

    def walk(value: object, path: str) -> None:
        if isinstance(value, dict):
            if "value" in value and "source_span" in value:
                out.append(
                    ExtractedFieldOut(
                        name=path,
                        value=None if value["value"] is None else str(value["value"]),
                        source_span=value.get("source_span"),
                        verified=path not in unverified,
                    )
                )
                return
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else key)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}.{index}")

    order = {name: index for index, name in enumerate(field_order(schema_name))}
    walk(fields, "")
    # Unknown roots sort last, stably, so an extra field never displaces the
    # ones a reviewer is looking for.
    out.sort(key=lambda row: order.get(row.name.split(".")[0], len(order)))
    return out


@router.post(
    "/{decision_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve a decision and queue its side effects",
    description=(
        "Emits the same `decision.execute` event an auto-approved decision "
        "emits, so there is one execution path. Safe to call twice: the "
        "event's idempotency key is derived from the decision and action.\n\n"
        "Pass `override_outcome` when overruling the pipeline. The original "
        "outcome is kept beside it, because the disagreement rate per rule is "
        "what tells you when a threshold can widen."
    ),
    responses={**NOT_FOUND, 409: {"description": "Decision is not awaiting review"}},
)
def approve_decision(
    decision_id: uuid.UUID,
    body: ApproveRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    decision = require_decision_access(db, decision_id, user.org_id)

    # Already approved: return the existing event rather than 409. A retried
    # request is not an error, and the event layer dedupes it anyway.
    if decision.status in (DecisionStatus.approved, DecisionStatus.executed):
        return ApprovalResponse(decision_id=decision.id, status=str(decision.status))

    if decision.status is not DecisionStatus.pending_review:
        raise HTTPException(409, f"Decision is {decision.status}, not awaiting review")

    _require_authority(db, user, decision)

    if body.override_outcome is not None:
        _validate_override(body.override_outcome)
        decision.override_outcome = body.override_outcome
        decision.override_note = body.note

    decision.status = DecisionStatus.approved
    decision.reviewed_by = user.id
    decision.reviewed_at = datetime.now(UTC)
    db.commit()

    event = emit_execute(db, decision, action="approve_for_payment")
    return ApprovalResponse(
        decision_id=decision.id, status=str(decision.status), event_id=event.id
    )


@router.post(
    "/{decision_id}/reject",
    response_model=ApprovalResponse,
    summary="Reject a decision. Nothing is executed",
    description=(
        "Closes the case without a side effect. The rejection and its note "
        "stay on the row, because a rejected invoice is exactly the kind of "
        "thing somebody asks about later."
    ),
    responses={**NOT_FOUND, 409: {"description": "Decision is not awaiting review"}},
)
def reject_decision(
    decision_id: uuid.UUID,
    body: RejectRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    decision = require_decision_access(db, decision_id, user.org_id)

    if decision.status is DecisionStatus.rejected:
        return ApprovalResponse(decision_id=decision.id, status=str(decision.status))

    if decision.status is not DecisionStatus.pending_review:
        raise HTTPException(409, f"Decision is {decision.status}, not awaiting review")

    # Rejecting is an act on the case too, and a viewer may not perform it.
    # The amount limit does not apply: refusing to pay is never the risk a
    # ceiling exists to contain.
    if user.role not in APPROVERS:
        raise HTTPException(403, f"A {user.role} may not reject decisions")

    decision.status = DecisionStatus.rejected
    decision.override_outcome = str(Outcome.reject)
    decision.override_note = body.note
    decision.reviewed_by = user.id
    decision.reviewed_at = datetime.now(UTC)
    db.commit()
    return ApprovalResponse(decision_id=decision.id, status=str(decision.status))


def decision_amount(db: Session, decision: Decision) -> Decimal | None:
    """What this decision is worth, for the approval-limit check.

    Read from the extraction row rather than recomputed. An amount that
    could not be read comes back None, and a member with a ceiling cannot
    approve it: "we could not read the total" is not evidence that the
    total is under the limit.
    """
    if decision.extraction_id is None:
        return None
    extraction = db.get(Extraction, decision.extraction_id)
    if extraction is None:
        return None
    field = (extraction.fields or {}).get("total_incl_vat")
    if not isinstance(field, dict) or field.get("value") is None:
        return None
    try:
        return Decimal(str(field["value"]))
    except (ArithmeticError, ValueError):
        return None


def _require_authority(db: Session, user: CurrentUser, decision: Decision) -> None:
    """Role plus threshold, held on the membership (spec section 11)."""
    amount = decision_amount(db, decision)
    if user.may_approve(amount):
        return

    if user.role not in APPROVERS:
        raise HTTPException(403, f"A {user.role} may not approve decisions")
    if amount is None:
        raise HTTPException(
            403,
            "This decision has no readable total, so it cannot be checked against "
            "your approval limit. Somebody without a limit has to take it.",
        )
    raise HTTPException(
        403,
        f"This decision is for {amount}, above your approval limit of "
        f"{user.approval_limit}.",
    )


def _validate_override(outcome: str) -> None:
    try:
        parsed = Outcome(outcome)
    except ValueError as exc:
        raise HTTPException(422, f"Unknown outcome {outcome!r}") from exc
    if parsed not in OVERRIDABLE:
        raise HTTPException(
            422,
            f"{parsed} is not something a reviewer may choose. Automatic "
            "execution is authorised by a rule, not by a person approving one case.",
        )
