"""Approval: the human half of the split, and the one execute event.

Spec section 6. The decide workflow ends by writing a `decisions` row and
returning. A reviewer approving it, and the router auto-approving it, both
come through `emit_execute`, so there is exactly one path to a side effect
and the approval is just a different way to reach it.

The idempotency key is derived from the decision and the action, not
generated, so a reviewer who double-clicks approve creates one event and
one execution rather than two.
"""

import uuid

from sqlalchemy.orm import Session

from app.db.models import Decision as DecisionRow
from app.db.models import Event
from app.logging import get_logger

log = get_logger(__name__)


def execution_key(decision_id: uuid.UUID, action: str) -> str:
    """The idempotency key for one action on one decision.

    Used for both the event and the `executions` row, so a retry at either
    layer lands on the same key. Deriving it rather than generating it is
    what makes approve-twice safe (spec section 10).
    """
    return f"decision:{decision_id}:{action}"


def emit_execute(db: Session, decision: DecisionRow, action: str) -> Event:
    """Queue the side effects for an approved decision."""
    # Imported here, not at module scope: `create_event` reaches the Celery
    # task module, which imports every workflow, one of which imports this
    # file for `execution_key`. A function-level import is how the rest of
    # the codebase breaks that same cycle.
    from app.core.intake import create_event

    event, created = create_event(
        db,
        type="decision.execute",
        payload={
            "decision_id": str(decision.id),
            "action": action,
        },
        user_id=decision.user_id,
        idempotency_key=execution_key(decision.id, action),
    )
    log.info(
        "decision.execute.emitted",
        decision_id=str(decision.id),
        action=action,
        event_id=str(event.id),
        created=created,
    )
    return event
