"""Event intake: create-and-dispatch with idempotency.

Both the API (`POST /events`) and the webhook ingress funnel through here so
retried requests and re-delivered webhooks with the same idempotency key are
processed exactly once.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Event
from app.worker.tasks import dispatch_event


def create_event(
    db: Session,
    *,
    type: str,
    payload: dict,
    user_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> tuple[Event, bool]:
    """Create an event and dispatch it, or return the existing one for a
    repeated idempotency key. Returns (event, created)."""
    if idempotency_key:
        existing = db.scalar(select(Event).where(Event.idempotency_key == idempotency_key))
        if existing is not None:
            return existing, False

    event = Event(
        user_id=user_id,
        type=type,
        payload=payload,
        idempotency_key=idempotency_key,
        max_attempts=settings.event_max_attempts,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request inserted the same key first — return that one.
        db.rollback()
        existing = db.scalar(select(Event).where(Event.idempotency_key == idempotency_key))
        if existing is not None:
            return existing, False
        raise

    dispatch_event(event.id)
    return event, True
