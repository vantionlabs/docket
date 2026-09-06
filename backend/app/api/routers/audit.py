"""The audit log (spec section 15).

Boring, and the reason a finance director signs. One row per decision,
carrying what arrived, what was decided, who approved it, and what fired,
so the question an auditor asks a year later about the one invoice that
turned out to be wrong has an answer that fits on a line.

Exportable as CSV, because that is what actually gets sent to an auditor.
"""

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import UNAUTHORIZED, AuditRow
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import (
    Decision,
    DecisionCitation,
    DecisionStatus,
    Execution,
    ExecutionStatus,
    Extraction,
    SourceDocument,
    User,
)

router = APIRouter(prefix="/audit", tags=["audit"], responses=UNAUTHORIZED)

COLUMNS = [
    "decision_id",
    "created_at",
    "filename",
    "supplier",
    "amount",
    "currency",
    "outcome",
    "effective_outcome",
    "status",
    "rule_id",
    "grounding_passed",
    "citation_count",
    "reviewed_by_email",
    "reviewed_at",
    "override_outcome",
    "executed_reference",
]


def _field(fields: dict | None, name: str) -> str | None:
    value = (fields or {}).get(name)
    if isinstance(value, dict) and value.get("value") is not None:
        return str(value["value"])
    return None


def _rows(
    db: Session,
    org_id: uuid.UUID,
    status: DecisionStatus | None,
    since: datetime | None,
    limit: int,
    offset: int,
) -> list[AuditRow]:
    """One query per join rather than one per row: the audit log is the
    screen most likely to be opened on a year of data."""
    stmt = (
        select(Decision)
        .where(Decision.org_id == org_id)
        .order_by(Decision.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(Decision.status == status)
    if since is not None:
        stmt = stmt.where(Decision.created_at >= since)
    decisions = list(db.scalars(stmt))
    if not decisions:
        return []

    ids = [d.id for d in decisions]
    documents = {
        row.id: row
        for row in db.scalars(
            select(SourceDocument).where(
                SourceDocument.id.in_({d.document_id for d in decisions})
            )
        )
    }
    extractions = {
        row.id: row
        for row in db.scalars(
            select(Extraction).where(
                Extraction.id.in_({d.extraction_id for d in decisions if d.extraction_id})
            )
        )
    }
    citation_counts = dict(
        db.execute(
            select(DecisionCitation.decision_id, func.count())
            .where(DecisionCitation.decision_id.in_(ids))
            .group_by(DecisionCitation.decision_id)
        ).all()
    )
    executions = {
        row.decision_id: row
        for row in db.scalars(
            select(Execution).where(
                Execution.decision_id.in_(ids),
                Execution.status == ExecutionStatus.succeeded,
            )
        )
    }
    reviewers = {
        row.id: row.email
        for row in db.scalars(
            select(User).where(User.id.in_({d.reviewed_by for d in decisions if d.reviewed_by}))
        )
    }

    out: list[AuditRow] = []
    for decision in decisions:
        extraction = extractions.get(decision.extraction_id)
        fields = extraction.fields if extraction else {}
        execution = executions.get(decision.id)
        out.append(
            AuditRow(
                decision_id=decision.id,
                document_id=decision.document_id,
                filename=documents[decision.document_id].filename
                if decision.document_id in documents
                else "",
                supplier=_field(fields, "supplier"),
                amount=_field(fields, "total_incl_vat"),
                currency=_field(fields, "currency"),
                outcome=decision.outcome,
                effective_outcome=decision.effective_outcome,
                status=str(decision.status),
                rule_id=decision.rule_id,
                grounding_passed=decision.grounding_passed,
                citation_count=citation_counts.get(decision.id, 0),
                reviewed_by_email=reviewers.get(decision.reviewed_by),
                reviewed_at=decision.reviewed_at,
                override_outcome=decision.override_outcome,
                executed_reference=(execution.response or {}).get("external_reference")
                if execution
                else None,
                created_at=decision.created_at,
            )
        )
    return out


@router.get(
    "",
    response_model=list[AuditRow],
    summary="The audit log",
    description=(
        "Every decision this org has made, newest first, with the citation "
        "count, who reviewed it, and what the adapter returned."
    ),
)
def list_audit(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: DecisionStatus | None = Query(default=None),
    since: datetime | None = Query(default=None, description="ISO timestamp."),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AuditRow]:
    return _rows(db, user.org_id, status, since, limit, offset)


@router.get(
    "/export.csv",
    summary="The audit log as CSV",
    description="What actually gets sent to an auditor.",
    response_class=StreamingResponse,
)
def export_audit(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: DecisionStatus | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=10000, le=50000),
) -> StreamingResponse:
    rows = _rows(db, user.org_id, status, since, limit, 0)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.model_dump(mode="json").get(key, "") for key in COLUMNS})
    buffer.seek(0)

    stamp = datetime.now().strftime("%Y-%m-%d")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="docket-audit-{stamp}.csv"'},
    )
