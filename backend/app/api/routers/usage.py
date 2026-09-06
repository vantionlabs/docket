"""Usage + cost summary for the current user."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import UNAUTHORIZED
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import LlmUsage

router = APIRouter(prefix="/usage", tags=["usage"], responses=UNAUTHORIZED)


class UsageByOperation(BaseModel):
    operation: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class UsageSummary(BaseModel):
    window_days: int
    total_cost_usd: float = Field(description="Total spend in the window, USD.")
    by_operation: list[UsageByOperation]


@router.get(
    "",
    response_model=UsageSummary,
    summary="Your LLM usage + cost",
    description="Token counts and computed cost, grouped by operation, over the last N days.",
)
def usage_summary(
    days: int = 30,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UsageSummary:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(
            LlmUsage.operation,
            func.count().label("calls"),
            func.coalesce(func.sum(LlmUsage.input_tokens), 0),
            func.coalesce(func.sum(LlmUsage.output_tokens), 0),
            func.coalesce(func.sum(LlmUsage.cost_usd), 0.0),
        )
        .where(LlmUsage.user_id == user.id, LlmUsage.created_at >= since)
        .group_by(LlmUsage.operation)
    ).all()

    by_op = [
        UsageByOperation(
            operation=r[0],
            calls=r[1],
            input_tokens=r[2],
            output_tokens=r[3],
            cost_usd=round(r[4], 6),
        )
        for r in rows
    ]
    return UsageSummary(
        window_days=days,
        total_cost_usd=round(sum(o.cost_usd for o in by_op), 6),
        by_operation=by_op,
    )
