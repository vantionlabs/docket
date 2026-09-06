"""Generic event intake (the Launchpad pattern).

POST an event, get its id back, poll GET /events/{id} for the outcome.
Domain endpoints (like the documents API) create events internally; this
router also exposes the generic surface for webhooks and custom jobs.
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import NOT_FOUND, UNAUTHORIZED, EventIn, EventOut
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.intake import create_event as intake_event
from app.core.registry import registered_types
from app.db.engine import get_db
from app.db.models import Event

router = APIRouter(prefix="/events", tags=["events"], responses=UNAUTHORIZED)


@router.post(
    "",
    response_model=EventOut,
    status_code=202,
    summary="Submit an event for background processing",
    description=(
        "Persists an event and dispatches it to the worker, which runs the "
        "workflow registered for its `type`. Poll `GET /events/{id}` for the "
        "outcome (`queued` → `processing` → `done`/`failed`).\n\n"
        "Send an `Idempotency-Key` header to make retries safe: a repeated "
        "key returns the original event instead of processing again."
    ),
    responses={422: {"description": "Unknown event type"}},
)
def create_event(
    body: EventIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Event:
    if body.type not in registered_types():
        raise HTTPException(422, f"Unknown event type {body.type!r}")
    event, _created = intake_event(
        db,
        type=body.type,
        payload=body.payload,
        user_id=user.id,
        idempotency_key=idempotency_key,
    )
    return event


@router.get(
    "/{event_id}",
    response_model=EventOut,
    summary="Event status + result",
    responses=NOT_FOUND,
)
def get_event(
    event_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Event:
    event = db.get(Event, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(404, "Event not found")
    return event
