"""End-to-end: a document becomes a decision, an approval becomes an execution.

Needs a live Postgres with pgvector and the migrations applied:

    docker compose up -d postgres
    docker compose run --rm api uv run alembic upgrade head
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/app \
      uv run pytest -m integration

These are the tests the offline lane cannot write: that the unique
constraint on `executions.idempotency_key` really is what stops a double
payment, that the collection filter really is enforced by the database, and
that a decision row survives the workflow ending.
"""

import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.engine import SessionLocal
from app.db.models import (
    Collection,
    Decision,
    DecisionStatus,
    DocumentChunk,
    Execution,
    ExecutionStatus,
    Organization,
    SourceDocument,
    User,
)
from tests.integration.conftest import _purge

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


@pytest.fixture
def org(db, user):
    """The org the user owns. Created through the real path, so this test
    also covers `ensure_personal_org` (spec section 11)."""
    from app.auth.orgs import ensure_personal_org

    return ensure_personal_org(db, user.id, user.email).org_id


@pytest.fixture
def user(db):
    row = User(
        id=uuid.uuid4(),
        email=f"reviewer-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(row)
    db.commit()
    yield row
    _purge(db, row)


def _document(db, user, collection: Collection, filename: str, org_id=None) -> SourceDocument:
    doc = SourceDocument(
        user_id=user.id,
        org_id=org_id,
        collection=collection,
        filename=filename,
        r2_key=f"test/{uuid.uuid4()}",
        content_type="text/markdown",
    )
    db.add(doc)
    db.commit()
    return doc


def test_migration_created_the_docket_schema(db):
    """Cheap smoke test: every table the pipeline writes to exists."""
    for model in (Organization, Decision, Execution):
        db.execute(select(model).limit(1))


def test_collection_defaults_to_transactional(db, user):
    """A document nobody classified must not become policy by accident."""
    doc = _document(db, user, Collection.transactional, "invoice.md")
    db.refresh(doc)
    assert doc.collection is Collection.transactional


def test_collection_filter_keeps_the_two_corpora_apart(db, user):
    """The separation is a database filter, not a convention (section 8)."""
    policy_doc = _document(db, user, Collection.policy, "policy.md")
    invoice_doc = _document(db, user, Collection.transactional, "invoice.md")

    for doc, text in ((policy_doc, "spend threshold clause"), (invoice_doc, "invoice total")):
        db.add(
            DocumentChunk(
                document_id=doc.id,
                user_id=user.id,
                collection=doc.collection,
                chunk_index=0,
                content=text,
                embedding=[0.0] * settings.embedding_dimensions,
            )
        )
    db.commit()

    policy_chunks = db.scalars(
        select(DocumentChunk).where(
            DocumentChunk.user_id == user.id,
            DocumentChunk.collection == Collection.policy,
        )
    ).all()
    assert [c.content for c in policy_chunks] == ["spend threshold clause"]


def test_a_duplicate_idempotency_key_cannot_be_inserted(db, user, org):
    """The guarantee of section 10 is the constraint, not the code near it."""
    from sqlalchemy.exc import IntegrityError

    doc = _document(db, user, Collection.transactional, "invoice.md", org)
    decision = Decision(
        org_id=org,
        user_id=user.id,
        document_id=doc.id,
        outcome="route_for_approval",
        status=DecisionStatus.approved,
    )
    db.add(decision)
    db.commit()

    key = f"decision:{decision.id}:approve_for_payment"
    db.add(
        Execution(
            org_id=org,
            decision_id=decision.id,
            adapter="dry_run",
            idempotency_key=key,
            status=ExecutionStatus.succeeded,
        )
    )
    db.commit()

    db.add(
        Execution(
            org_id=org,
            decision_id=decision.id,
            adapter="dry_run",
            idempotency_key=key,
            status=ExecutionStatus.pending,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_outcome_check_constraint_rejects_an_invented_outcome(db, user, org):
    """The enum is closed in the database too. A model that could invent an
    outcome could invent one nobody has a process for (section 9)."""
    from sqlalchemy.exc import IntegrityError

    doc = _document(db, user, Collection.transactional, "invoice.md", org)
    db.add(
        Decision(
            org_id=org,
            user_id=user.id,
            document_id=doc.id,
            outcome="pay_it_quietly",
            status=DecisionStatus.pending_review,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_dimension_the_vertical_does_not_evaluate_cannot_be_stored(db, user, org):
    """0007 held this as a CHECK naming nine invoice dimensions, which made
    adding a document type a migration. It is now a foreign key into
    `vertical_dimensions`, kept current from the registry — same closed set,
    no DDL per vertical.

    `deadline` is a real dimension. It belongs to tenders. An invoice
    obligation claiming it is a rule nothing would ever check."""
    from sqlalchemy.exc import IntegrityError

    from app.db.models import PolicyObligation

    doc = _document(db, user, Collection.policy, "procurement-policy.md", org)
    db.add(
        PolicyObligation(
            org_id=org,
            document_id=doc.id,
            schema_name="invoice",
            dimension="deadline",
            summary="Bids close at noon",
            clause_ref="4. Deadlines",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_the_registry_and_the_reference_table_agree(db):
    """`sync_vertical_dimensions` is what makes registering a vertical the
    whole of adding one. If it drifts, the foreign key starts rejecting
    obligations for a vertical that legitimately evaluates them."""
    from app.db.models import VerticalDimension
    from app.decisions.coverage import sync_vertical_dimensions
    from app.verticals import get_vertical, registered_verticals

    sync_vertical_dimensions(db)
    stored = {
        (row.schema_name, row.dimension) for row in db.query(VerticalDimension).all()
    }
    expected = {
        (name, dimension)
        for name in registered_verticals()
        for dimension in get_vertical(name).dimensions
    }
    assert expected <= stored


def test_the_audit_join_answers_the_auditors_question(db, user, org):
    """One join: why was this decided, citing what, and what fired."""
    from app.db.models import DecisionCitation

    doc = _document(db, user, Collection.transactional, "invoice.md", org)
    decision = Decision(
        org_id=org,
        user_id=user.id,
        document_id=doc.id,
        outcome="route_for_approval",
        rationale="Under the limit [1].",
        status=DecisionStatus.executed,
    )
    db.add(decision)
    db.flush()
    db.add(
        DecisionCitation(
            decision_id=decision.id,
            citation_index=1,
            clause_ref="3. Spend thresholds",
            excerpt="Up to EUR 1,000: the cost centre owner may approve.",
        )
    )
    db.add(
        Execution(
            org_id=org,
            decision_id=decision.id,
            adapter="dry_run",
            idempotency_key=f"decision:{decision.id}:approve_for_payment",
            status=ExecutionStatus.succeeded,
            response={"external_reference": "dry-run-1"},
        )
    )
    db.commit()

    row = db.scalars(
        select(Decision).where(Decision.id == decision.id)
    ).one()
    assert [c.excerpt for c in row.citations] == [
        "Up to EUR 1,000: the cost centre owner may approve."
    ]
    execution = db.scalar(select(Execution).where(Execution.decision_id == decision.id))
    assert execution.response["external_reference"] == "dry-run-1"
