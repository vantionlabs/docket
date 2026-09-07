"""Intake: three doors, one seam (spec sections 4 and 5).

What matters here is that the pipeline a document enters is decided by what
the document IS, not by how it arrived, and that arriving twice is not the
same as arriving twice as much work.
"""

import base64
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.document_intake import PIPELINE, receive_document
from app.db.models import Collection, DocumentStatus


def _document(collection=Collection.transactional):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        collection=collection,
        status=DocumentStatus.pending_upload,
    )


@pytest.fixture
def db():
    session = MagicMock()
    session.scalar.return_value = None  # no prior intake
    return session


@pytest.fixture
def created(monkeypatch):
    """Capture the events intake would queue, without a Celery broker."""
    events: list[dict] = []

    def _create_event(_db, *, type, payload, user_id=None, idempotency_key=None):
        events.append({"type": type, "payload": payload, "key": idempotency_key})
        return SimpleNamespace(id=uuid.uuid4()), True

    # Patched where it is defined: `receive_document` imports it inside the
    # function to break an import cycle, so there is no module-level name.
    monkeypatch.setattr("app.core.intake.create_event", _create_event)
    return events


# --- the collection decides the pipeline, not the door ------------------


def test_a_transactional_document_goes_to_the_decision_pipeline(db, created):
    document = _document(Collection.transactional)
    receive_document(db, document, source="upload")
    assert created[0]["type"] == "document.decide"


def test_a_policy_document_goes_to_ingestion(db, created):
    """Chunked, embedded and indexed into obligations. Deciding a policy
    against itself would be nonsense."""
    document = _document(Collection.policy)
    receive_document(db, document, source="upload")
    assert created[0]["type"] == "document.ingest"


@pytest.mark.parametrize("source", ["upload", "webhook", "schedule", "email"])
def test_the_door_does_not_change_the_pipeline(db, created, source):
    receive_document(db, _document(Collection.transactional), source=source)
    assert created[-1]["type"] == "document.decide"


def test_every_collection_has_a_pipeline():
    """A collection with no entry here would raise a KeyError at intake,
    which is a bad place to discover a missing branch."""
    assert set(PIPELINE) == set(Collection)


# --- arriving twice ------------------------------------------------------


def test_a_repeated_external_ref_queues_nothing(db, created):
    db.scalar.return_value = SimpleNamespace(document_id=uuid.uuid4())
    event, was_created = receive_document(
        db, _document(), source="webhook", external_ref="supplier-portal-88213"
    )
    assert event is None
    assert was_created is False
    assert created == []


def test_a_lost_race_queues_nothing(db, created):
    """Two concurrent deliveries both see no prior intake. The unique
    constraint is what actually stops the second, not the check above it."""
    from sqlalchemy.exc import IntegrityError

    db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    event, was_created = receive_document(
        db, _document(), source="webhook", external_ref="same-ref"
    )
    assert event is None
    assert was_created is False
    assert created == []
    db.rollback.assert_called()


def test_the_event_key_is_derived_from_the_document(db, created):
    """Re-queueing the same document is safe however it got here."""
    document = _document()
    receive_document(db, document, source="upload")
    assert created[0]["key"] == f"document.decide:{document.id}"


def test_intake_marks_the_document_uploaded(db, created):
    document = _document()
    receive_document(db, document, source="upload")
    assert document.status is DocumentStatus.uploaded


# --- the webhook door ----------------------------------------------------


def _ctx(payload):
    from app.core.task_context import TaskContext

    return TaskContext(
        event_id=uuid.uuid4(),
        event_type="webhook.document",
        payload=payload,
        user_id=None,
        db=MagicMock(),
    )


def test_a_webhook_without_an_owner_is_rejected_not_guessed():
    """A document filed against the wrong tenant is worse than one that
    failed to arrive, because the second gets noticed."""
    from app.workflows.webhook_document import ResolveOwner

    with pytest.raises(ValueError, match="owner_email"):
        ResolveOwner().process(_ctx({"content_base64": "eA=="}))


def test_an_unknown_owner_is_rejected():
    from app.workflows.webhook_document import ResolveOwner

    ctx = _ctx({"owner_email": "nobody@example.com"})
    ctx.db.scalar.return_value = None
    with pytest.raises(ValueError, match="no user for owner_email"):
        ResolveOwner().process(ctx)


def test_valid_content_decodes():
    from app.workflows.webhook_document import DecodeContent

    payload = {"content_base64": base64.b64encode(b"# INVOICE").decode()}
    ctx = DecodeContent().process(_ctx(payload))
    assert ctx.metadata["raw"] == b"# INVOICE"


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({}, "no content_base64"),
        ({"content_base64": "not base64!!"}, "not valid base64"),
        ({"content_base64": ""}, "no content_base64"),
    ],
)
def test_bad_content_is_rejected(payload, match):
    from app.workflows.webhook_document import DecodeContent

    with pytest.raises(ValueError, match=match):
        DecodeContent().process(_ctx(payload))


def test_oversized_content_is_rejected():
    from app.workflows.webhook_document import MAX_BYTES, DecodeContent

    payload = {"content_base64": base64.b64encode(b"x" * (MAX_BYTES + 1)).decode()}
    with pytest.raises(ValueError, match="over the"):
        DecodeContent().process(_ctx(payload))


def test_the_webhook_takes_no_urls():
    """Fetching a URL from an inbound payload would turn a leaked signing
    secret into an SSRF primitive. Content is inline or it is nothing."""
    import inspect

    from app.workflows import webhook_document

    source = inspect.getsource(webhook_document)
    assert "httpx" not in source
    assert "requests" not in source
