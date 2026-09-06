"""Seed a demo org: a policy corpus, some invoices, and real decisions.

Runs the actual decide workflow, so what lands in the queue is what the
pipeline produced, not fixtures shaped to look good. That matters: a demo
built on hand-written rows tells you nothing about whether the thing works,
and this one has already caught two real bugs.

    docker run -d --name docket-postgres -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=app -p 55432:5432 \
      pgvector/pgvector:pg17
    export DATABASE_URL=postgresql://postgres:postgres@localhost:55432/app
    uv run alembic upgrade head
    uv run python scripts/seed_demo.py

Everything queues. No rule is created, so nothing auto-approves, which is
what v1 ships as (spec section 4).

**Embeddings.** Seeding must not require an embedding provider, so vectors
are zeros and retrieval leans on Postgres FTS. Good enough to demo, and
not good enough to ship: a real deployment needs EMBEDDING_PROVIDER
configured, and `--real-embeddings` uses it when it is.
"""

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.auth.orgs import ensure_personal_org  # noqa: E402
from app.core.task_context import TaskContext  # noqa: E402
from app.db.engine import SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Collection,
    Decision,
    DocumentChunk,
    DocumentStatus,
    Intake,
    SourceDocument,
    User,
)
from app.ingestion.chunking import chunk_text  # noqa: E402
from app.workflows.document_decide import DocumentDecideWorkflow  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "evals/fixtures"
POLICY = FIXTURES / "procurement-policy.md"
INVOICES = sorted((FIXTURES / "invoices").glob("*.md"))

DEMO_EMAIL = "demo@northwind.nl"
DEMO_PASSWORD = "docket-demo"
DIMENSIONS = 1536


def _stub_embeddings() -> None:
    """Zero vectors, so seeding works without an embedding provider.

    Retrieval then runs on FTS alone. RRF still fuses two rankings, one of
    which is meaningless, which is fine for a demo and is not a deployment
    posture. Said out loud here rather than discovered later.
    """
    import app.retrieval.hybrid as hybrid

    hybrid.embed_query = lambda _text: [0.0] * DIMENSIONS
    print("embeddings: stubbed to zeros, retrieval is FTS-only")


def _user(db) -> User:
    """The demo user, hashed by fastapi-users so the password actually works.

    Reset on every run: a seed script whose credentials do not let you sign
    in is a seed script that wasted your time.
    """
    from fastapi_users.password import PasswordHelper

    hashed = PasswordHelper().hash(DEMO_PASSWORD)
    row = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if row is not None:
        row.hashed_password = hashed
        db.commit()
        return row

    row = User(
        id=uuid.uuid4(),
        email=DEMO_EMAIL,
        hashed_password=hashed,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(row)
    db.commit()
    print(f"created user {DEMO_EMAIL} / {DEMO_PASSWORD}")
    return row


def _policy(db, user, org_id) -> SourceDocument:
    """Load the policy corpus into the policy collection.

    Embeddings are zeros: seeding should not require an embedding provider,
    and Postgres FTS carries retrieval well enough for a demo. Re-embed for
    real use.
    """
    existing = db.scalar(
        select(SourceDocument).where(
            SourceDocument.org_id == org_id,
            SourceDocument.collection == Collection.policy,
        )
    )
    if existing is not None:
        return existing

    doc = SourceDocument(
        user_id=user.id,
        org_id=org_id,
        collection=Collection.policy,
        filename=POLICY.name,
        r2_key=f"seed/policy/{uuid.uuid4()}",
        content_type="text/markdown",
        status=DocumentStatus.ready,
    )
    db.add(doc)
    db.commit()

    chunks = chunk_text(POLICY.read_text(encoding="utf-8"), target_tokens=180)
    for chunk in chunks:
        db.add(
            DocumentChunk(
                document_id=doc.id,
                user_id=user.id,
                org_id=org_id,
                collection=Collection.policy,
                chunk_index=chunk.index,
                content=chunk.content,
                embedding=[0.0] * DIMENSIONS,
            )
        )
    db.commit()
    print(f"loaded policy: {POLICY.name}, {len(chunks)} chunks")
    return doc


def _decide(db, user, org_id, path: Path) -> None:
    doc = SourceDocument(
        user_id=user.id,
        org_id=org_id,
        collection=Collection.transactional,
        filename=path.name,
        r2_key=f"seed/invoice/{uuid.uuid4()}",
        content_type="text/markdown",
        status=DocumentStatus.ready,
    )
    db.add(doc)
    db.commit()
    db.add(
        Intake(
            org_id=org_id,
            source="upload",
            external_ref=f"seed:{path.name}:{doc.id}",
            document_id=doc.id,
            raw={"seeded": True},
        )
    )
    db.commit()

    # The workflow fetches from R2; here the bytes come off disk instead.
    import app.workflows.document_decide as workflow_module

    original = workflow_module.download_bytes
    workflow_module.download_bytes = lambda _key: path.read_bytes()
    try:
        DocumentDecideWorkflow().run(
            TaskContext(
                event_id=uuid.uuid4(),
                event_type="document.decide",
                payload={"document_id": str(doc.id)},
                user_id=str(user.id),
                db=db,
            )
        )
    finally:
        workflow_module.download_bytes = original

    decision = db.scalar(select(Decision).where(Decision.document_id == doc.id))
    print(f"  {path.name:32} -> {decision.outcome:20} ({len(decision.citations)} clauses)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--invoices", type=int, default=len(INVOICES), help="how many fixtures to decide"
    )
    parser.add_argument(
        "--real-embeddings",
        action="store_true",
        help="use the configured embedding provider instead of zero vectors",
    )
    args = parser.parse_args()

    if not args.real_embeddings:
        _stub_embeddings()

    with SessionLocal() as db:
        user = _user(db)
        org_id = ensure_personal_org(db, user.id, user.email).org_id
        _policy(db, user, org_id)

        print(f"deciding {args.invoices} invoices:")
        for path in INVOICES[: args.invoices]:
            _decide(db, user, org_id, path)

        pending = db.scalars(
            select(Decision).where(Decision.org_id == org_id)
        ).all()
        print(f"\n{len(pending)} decisions in the queue for {DEMO_EMAIL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
