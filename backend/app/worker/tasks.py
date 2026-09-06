"""Celery tasks: run events through their registered workflows.

The task is thin: load the event, mark it processing, run the registered
workflow with a fresh DB session, record the outcome. Reliability lives
here too:

- **Retries.** A workflow that raises is retried with exponential backoff
  up to the event's `max_attempts`, then dead-lettered (status=failed).
- **Dead-letter.** Exhausted events stay as `failed` rows with the error,
  never silently dropped — inspect them with `GET /events/{id}`.
- **Recovery.** `sweep_stale_events` (run by Celery beat) requeues events a
  crashed worker left stuck in `processing`.

All domain logic lives in workflow nodes; this module only orchestrates.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

# Importing workflows registers them with the registry.
import app.workflows  # noqa: F401  (side-effect import)
from app.config import settings
from app.core.registry import workflow_for
from app.core.task_context import TaskContext
from app.db.engine import SessionLocal
from app.db.models import Event, EventStatus
from app.logging import get_logger
from app.worker.celery_app import celery_app
from app.worker.retry import backoff_seconds

log = get_logger(__name__)


@celery_app.task(name="app.run_event", bind=True, acks_late=True, max_retries=None)
def run_event(self, event_id: str) -> None:
    with SessionLocal() as db:
        event = db.get(Event, uuid.UUID(event_id))
        if event is None:
            log.error("event.missing", event_id=event_id)
            return
        if event.status in (EventStatus.done, EventStatus.failed):
            log.info("event.skipped", event_id=event_id, status=str(event.status))
            return

        event.status = EventStatus.processing
        event.attempts += 1
        attempt = event.attempts
        max_attempts = event.max_attempts
        db.commit()

        ctx = TaskContext(
            event_id=event.id,
            event_type=event.type,
            payload=dict(event.payload or {}),
            user_id=event.user_id,
            db=db,
        )
        workflow = None
        try:
            workflow = workflow_for(event.type)()
            ctx = workflow.run(ctx)
            event.status = EventStatus.done
            event.result = ctx.to_result()
            event.error = None
            db.commit()
            log.info("event.done", event_id=event_id, type=event.type, attempt=attempt)
            return
        except Exception as exc:  # noqa: BLE001 — the task boundary catches everything
            db.rollback()
            message = f"{type(exc).__name__}: {exc}"[:1000]

            if attempt < max_attempts:
                # Transient failure: schedule a retry with backoff.
                event = db.get(Event, uuid.UUID(event_id))
                if event is not None:
                    event.status = EventStatus.queued
                    event.error = f"attempt {attempt}/{max_attempts} failed: {message}"
                    db.commit()
                delay = backoff_seconds(attempt)
                log.warning(
                    "event.retry", event_id=event_id, attempt=attempt, delay=delay, error=message
                )
                raise self.retry(exc=exc, countdown=delay) from exc

            # Exhausted: dead-letter. Run the workflow's cleanup hook so a
            # failed job never wedges downstream state (e.g. a document stuck
            # in `processing`).
            if workflow is not None:
                try:
                    workflow.on_failure(ctx, exc)
                except Exception:  # noqa: BLE001 — cleanup must not mask the failure
                    log.exception("event.on_failure_hook_failed", event_id=event_id)
                    db.rollback()
            event = db.get(Event, uuid.UUID(event_id))
            if event is not None:
                event.status = EventStatus.failed
                event.error = message
                db.commit()
            log.error("event.dead_letter", event_id=event_id, attempts=attempt, error=message)


@celery_app.task(name="app.sweep_stale_events")
def sweep_stale_events() -> int:
    """Recover events a crashed worker left stuck in `processing`.

    Requeues those with retries left; dead-letters the rest. Scheduled by
    Celery beat (see celery_app.beat_schedule).
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.stale_processing_minutes)
    recovered = 0
    with SessionLocal() as db:
        stale = db.scalars(
            select(Event).where(
                Event.status == EventStatus.processing, Event.updated_at < cutoff
            )
        ).all()
        for event in stale:
            if event.attempts < event.max_attempts:
                event.status = EventStatus.queued
                event.error = "recovered: worker did not finish; requeued"
                db.commit()
                dispatch_event(event.id)
            else:
                event.status = EventStatus.failed
                event.error = "stale: worker did not finish and retries exhausted"
                db.commit()
            recovered += 1
        if recovered:
            log.warning("events.swept", count=recovered)
    return recovered


def dispatch_event(event_id: uuid.UUID) -> None:
    """Enqueue an event for the worker. Call after committing the event row."""
    run_event.delay(str(event_id))
