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

from sqlalchemy import func, select  # noqa: E402

from app.auth.orgs import ensure_personal_org  # noqa: E402
from app.config import settings
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
from app.ingestion.context import contextualize  # noqa: E402
from app.llm.embeddings import embed_documents, embeddings_available  # noqa: E402
from app.workflows.document_decide import DocumentDecideWorkflow  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "evals/fixtures"
CORPUS_DIR = FIXTURES / "corpus"
POLICY = FIXTURES / "procurement-policy.md"
INVOICES = sorted((FIXTURES / "invoices").glob("*.md"))

DEMO_EMAIL = "demo@northwind.nl"
DEMO_PASSWORD = "docket-demo"
# Follows config: a test that restates the width breaks on every
# embedding-model change and tells you nothing useful when it does.
DIMENSIONS = settings.embedding_dimensions


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


def _policy_documents() -> list[Path]:
    """The corpus to load: the generated one if it exists, else the single
    hand-written policy.

    The generated corpus has distractors in it, which is the only version
    where retrieval can actually fail and therefore the only version worth
    measuring against.
    """
    generated = sorted(CORPUS_DIR.glob("*.md"))
    return generated or [POLICY]


def _policy(db, user, org_id, path: Path) -> SourceDocument:
    """Load one policy document into the policy collection."""
    existing = db.scalar(
        select(SourceDocument).where(
            SourceDocument.org_id == org_id,
            SourceDocument.collection == Collection.policy,
            SourceDocument.filename == path.name,
        )
    )
    if existing is not None:
        return existing

    doc = SourceDocument(
        user_id=user.id,
        org_id=org_id,
        collection=Collection.policy,
        filename=path.name,
        r2_key=f"seed/policy/{uuid.uuid4()}",
        content_type="text/markdown",
        status=DocumentStatus.ready,
    )
    db.add(doc)
    db.commit()

    document_text = path.read_text(encoding="utf-8")
    chunks = chunk_text(document_text, target_tokens=180)

    # Embed the way ingestion does: contextualized, as documents. Falls back
    # to zero vectors only when no provider is configured, so seeding still
    # works on a machine with no key.
    available, reason = embeddings_available()
    if available:
        vectors = embed_documents(
            [
                contextualize(chunk.content, path.name, document_text=document_text)
                for chunk in chunks
            ]
        )
    else:
        vectors = [[0.0] * DIMENSIONS for _ in chunks]

    for chunk, vector in zip(chunks, vectors, strict=True):
        db.add(
            DocumentChunk(
                document_id=doc.id,
                user_id=user.id,
                org_id=org_id,
                collection=Collection.policy,
                chunk_index=chunk.index,
                content=chunk.content,
                embedding=vector,
            )
        )
    db.commit()
    print(f"  {path.name:44} {len(chunks):3} chunks")
    _index_obligations(db, doc, org_id)
    return doc


def _index_obligations(db, doc, org_id) -> None:
    """Index the policy into obligations, so coverage checking has an index.

    Normally the IndexObligations node does this during ingest. The seed
    writes chunks directly (no R2, no worker), so it calls the same
    extraction here rather than leaving the demo with coverage silently
    switched off.
    """
    from app.db.models import PolicyObligation
    from app.decisions.coverage import extract_obligations
    from app.decisions.policy import _clause_ref

    existing = db.scalar(
        select(func.count())
        .select_from(PolicyObligation)
        .where(PolicyObligation.document_id == doc.id)
    )
    if existing:
        print(f"policy already indexed: {existing} obligations")
        return

    stored = 0
    for chunk in db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.chunk_index)
    ):
        ref = _clause_ref(doc.filename, chunk.content, chunk.chunk_index)
        for obligation in extract_obligations(
                chunk.content, ref, document_title=doc.filename
            ):
            db.add(
                PolicyObligation(
                    org_id=org_id,
                    document_id=doc.id,
                    chunk_id=chunk.id,
                    dimension=obligation["dimension"],
                    summary=obligation["summary"],
                    clause_ref=ref,
                    schema_name=obligation.get("governs", "invoice"),
                    in_force=obligation.get("in_force", True),
                    always_applies=obligation.get("always_applies", False),
                    threshold=obligation.get("threshold"),
                )
            )
            stored += 1
    db.commit()
    print(f"indexed the policy into {stored} obligations")


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

        documents = _policy_documents()
        print(f"loading policy corpus ({len(documents)} documents):")
        for path in documents:
            _policy(db, user, org_id, path)

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
