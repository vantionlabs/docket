"""The whole M2 pipeline, against a real database and a real model.

A document goes in, a decision comes out with citations to policy clauses
retrieved from the database, a human approves it, and a side effect is
recorded exactly once. This is the test that proves the two workflows join
up; everything else in the offline lane proves the pieces.

    docker run -d --name docket-postgres -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=app -p 55432:5432 \
      pgvector/pgvector:pg17
    DATABASE_URL=postgresql://postgres:postgres@localhost:55432/app \
      uv run alembic upgrade head
    DATABASE_URL=... uv run pytest -m integration

What this test does NOT check is retrieval quality. Embeddings are stubbed
to zeros, because the machine that runs this has an Anthropic key and no
embedding provider, so retrieval here leans entirely on Postgres FTS. The
plumbing is real; the ranking is not under test. Retrieval recall belongs
in the eval harness (spec section 13), not here.
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.task_context import TaskContext
from app.db.engine import SessionLocal
from app.db.models import (
    Collection,
    Decision,
    DecisionCitation,
    DecisionStatus,
    DocumentChunk,
    Execution,
    ExecutionStatus,
    Extraction,
    SourceDocument,
    User,
)
from app.decisions.models import Outcome
from app.ingestion.chunking import chunk_text
from app.workflows.decision_execute import DecisionExecuteWorkflow
from app.workflows.document_decide import DocumentDecideWorkflow
from tests.integration.conftest import _purge

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1].parent / "evals/fixtures"
POLICY = FIXTURES / "procurement-policy.md"
INVOICE = FIXTURES / "invoices/02-over-threshold-no-po.md"

DIMENSIONS = 1536


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def user(db):
    row = User(
        id=uuid.uuid4(),
        email=f"e2e-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(row)
    db.commit()
    yield row
    _purge(db, row)


@pytest.fixture
def org(db, user):
    from app.auth.orgs import ensure_personal_org

    return ensure_personal_org(db, user.id, user.email).org_id


@pytest.fixture
def seeded(db, user, org, monkeypatch):
    """A policy corpus in the database, and an invoice waiting to be decided."""
    policy_doc = SourceDocument(
        user_id=user.id,
        org_id=org,
        collection=Collection.policy,
        filename="procurement-policy.md",
        r2_key=f"test/policy/{uuid.uuid4()}",
        content_type="text/markdown",
    )
    invoice_doc = SourceDocument(
        user_id=user.id,
        org_id=org,
        collection=Collection.transactional,
        filename=INVOICE.name,
        r2_key=f"test/invoice/{uuid.uuid4()}",
        content_type="text/markdown",
    )
    db.add_all([policy_doc, invoice_doc])
    db.commit()

    # Chunk the policy the way ingestion would, but with zero vectors: FTS
    # carries retrieval here (see the module docstring).
    for chunk in chunk_text(POLICY.read_text(encoding="utf-8"), target_tokens=180):
        db.add(
            DocumentChunk(
                document_id=policy_doc.id,
                user_id=user.id,
                org_id=org,
                collection=Collection.policy,
                chunk_index=chunk.index,
                content=chunk.content,
                embedding=[0.0] * DIMENSIONS,
            )
        )
    db.commit()

    monkeypatch.setattr(
        "app.workflows.document_decide.download_bytes",
        lambda key: INVOICE.read_bytes(),
    )
    monkeypatch.setattr("app.retrieval.hybrid.embed_query", lambda text: [0.0] * DIMENSIONS)
    # The event row is what matters; enqueueing it needs a Redis this test
    # does not have, and the execute workflow is run directly below.
    monkeypatch.setattr("app.core.intake.dispatch_event", lambda event_id: None)

    return policy_doc, invoice_doc


def decision_outcome_is_not_auto(db, document_id) -> bool:
    row = db.scalar(select(Decision).where(Decision.document_id == document_id))
    return row is not None and row.outcome != str(Outcome.auto_approve)


def _ctx(db, event_type: str, payload: dict, user) -> TaskContext:
    return TaskContext(
        event_id=uuid.uuid4(),
        event_type=event_type,
        payload=payload,
        user_id=str(user.id),
        db=db,
    )


def test_document_becomes_a_queued_decision_with_real_citations(db, user, seeded):
    _policy_doc, invoice_doc = seeded

    ctx = DocumentDecideWorkflow().run(
        _ctx(db, "document.decide", {"document_id": str(invoice_doc.id)}, user)
    )

    # Extraction landed, with spans checked against the document.
    extraction = db.scalar(
        select(Extraction).where(Extraction.document_id == invoice_doc.id)
    )
    assert extraction is not None
    assert extraction.schema_name == "invoice"
    assert extraction.fields["supplier"]["value"] == "Fabrikam Office Supplies BV"
    # Span verification is a quality measure, not an invariant, so it belongs
    # in the eval harness (spec section 13) rather than as a pass/fail here.
    # What IS invariant is the rail: an unverified field can never auto-approve.
    if extraction.unverified_fields:
        assert decision_outcome_is_not_auto(db, invoice_doc.id)

    decision = db.scalar(select(Decision).where(Decision.document_id == invoice_doc.id))
    assert decision is not None

    # Nothing auto-approves: no rule row exists, so rail 3 holds it back.
    assert decision.status is DecisionStatus.pending_review
    assert decision.rule_id is None
    assert decision.outcome != str(Outcome.auto_approve)

    # Every outcome except needs_human must point at the policy it acted on.
    # Asserting "there are citations" outright would be asserting on model
    # output, which flakes; this is the invariant the rails guarantee whatever
    # the model returns.
    citations = db.scalars(
        select(DecisionCitation).where(DecisionCitation.decision_id == decision.id)
    ).all()
    if decision.outcome == str(Outcome.needs_human):
        # Declining to decide needs no policy support. It does need a reason.
        assert decision.rail_notes or decision.unmet_conditions
    else:
        assert citations, f"{decision.outcome} with no citations should not have shipped"

    for citation in citations:
        assert citation.excerpt
        chunk = db.get(DocumentChunk, citation.chunk_id)
        assert chunk is not None
        assert chunk.collection is Collection.policy, (
            "a decision cited something outside the policy collection"
        )

    # The workflow ran to the end rather than waiting for anybody.
    assert "Done" in ctx.nodes
    assert "EmitExecute" not in ctx.nodes


def test_approval_executes_once_even_when_the_event_is_replayed(db, user, seeded):
    _policy_doc, invoice_doc = seeded
    DocumentDecideWorkflow().run(
        _ctx(db, "document.decide", {"document_id": str(invoice_doc.id)}, user)
    )
    decision = db.scalar(select(Decision).where(Decision.document_id == invoice_doc.id))

    # The human half of the split.
    from datetime import UTC, datetime

    from app.decisions.approval import emit_execute

    decision.status = DecisionStatus.approved
    decision.reviewed_by = user.id
    decision.reviewed_at = datetime.now(UTC)
    db.commit()
    event = emit_execute(db, decision, action="approve_for_payment")

    payload = {"decision_id": str(decision.id), "action": "approve_for_payment"}
    DecisionExecuteWorkflow().run(_ctx(db, "decision.execute", payload, user))

    db.refresh(decision)
    assert decision.status is DecisionStatus.executed

    execution = db.scalar(select(Execution).where(Execution.decision_id == decision.id))
    assert execution.status is ExecutionStatus.succeeded
    assert execution.adapter == "dry_run"
    assert execution.response["external_reference"].startswith("dry-run-")
    # The adapter saw what was on the page, read back from the extraction row.
    assert execution.request["supplier"] == "Fabrikam Office Supplies BV"
    first_id = execution.id

    # Replay the same event: at-least-once delivery must not pay twice.
    DecisionExecuteWorkflow().run(_ctx(db, "decision.execute", payload, user))
    executions = db.scalars(
        select(Execution).where(Execution.decision_id == decision.id)
    ).all()
    assert len(executions) == 1
    assert executions[0].id == first_id

    # And approving again emits the same event, not a second one.
    assert emit_execute(db, decision, action="approve_for_payment").id == event.id
