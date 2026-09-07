"""Intake: the one place a document becomes work (spec sections 4 and 5).

Three doors lead here — upload, signed webhook, scheduled pull — and they
all arrive at the same function, because what happens next has nothing to do
with how the document turned up. That is also why `intakes` exists as a
table: the audit trail's first question is "what arrived", and it should
have the same answer whichever door was used.

**Which pipeline a document enters is decided by its collection, not by its
door.** A policy document gets chunked, embedded and indexed into
obligations. A transactional document gets decided. Nothing else makes
sense: chunking an invoice for chat would be a waste, and deciding a policy
against itself would be nonsense.

Deduplication is the `external_ref` unique constraint, not a check-then-act:
two concurrent deliveries of the same webhook both see no existing intake,
and only the constraint stops both from queueing work.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Collection, DocumentStatus, Event, Intake, SourceDocument
from app.logging import get_logger

log = get_logger(__name__)

# Which event type each collection's documents are worth.
PIPELINE = {
    Collection.policy: "document.ingest",
    Collection.transactional: "document.decide",
}


def receive_document(
    db: Session,
    document: SourceDocument,
    *,
    source: str,
    external_ref: str | None = None,
    raw: dict | None = None,
) -> tuple[Event | None, bool]:
    """Record that a document arrived, and queue what it needs.

    Returns `(event, created)`. `created` is False when this external_ref
    has been seen before, in which case nothing is queued and no second
    intake row is written.
    """
    if external_ref:
        existing = db.scalar(select(Intake).where(Intake.external_ref == external_ref))
        if existing is not None:
            log.info(
                "intake.duplicate", external_ref=external_ref, document_id=str(existing.document_id)
            )
            return None, False

    intake = Intake(
        org_id=document.org_id,
        source=source,
        external_ref=external_ref,
        document_id=document.id,
        raw=raw,
    )
    db.add(intake)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent delivery won the race. That one queued the work.
        db.rollback()
        log.info("intake.raced", external_ref=external_ref)
        return None, False

    document.status = DocumentStatus.uploaded
    db.commit()

    # Imported here, not at module scope: `create_event` reaches the Celery
    # task module, which imports every workflow, one of which imports this
    # file. Same cycle the approval seam breaks the same way.
    from app.core.intake import create_event

    event_type = PIPELINE[document.collection]
    event, created = create_event(
        db,
        type=event_type,
        payload={"document_id": str(document.id)},
        user_id=document.user_id,
        # Keyed on the document, so re-queueing the same document is safe
        # however it got here.
        idempotency_key=f"{event_type}:{document.id}",
    )
    log.info(
        "intake.received",
        source=source,
        collection=str(document.collection),
        document_id=str(document.id),
        event_type=event_type,
        event_id=str(event.id),
    )
    return event, created


def document_from_payload(
    db: Session,
    payload: dict,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID | None,
    r2_key: str,
) -> SourceDocument:
    """Build a SourceDocument row from an inbound payload.

    The caller has already put the bytes in storage; this only records them.
    """
    document = SourceDocument(
        user_id=user_id,
        org_id=org_id,
        collection=Collection(payload.get("collection", Collection.transactional)),
        filename=str(payload.get("filename") or "document"),
        r2_key=r2_key,
        content_type=str(payload.get("content_type") or "application/octet-stream"),
        size_bytes=payload.get("size_bytes"),
        status=DocumentStatus.uploaded,
    )
    db.add(document)
    db.commit()
    return document
