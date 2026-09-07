"""move document_chunks.embedding to 1024 dimensions (voyage-3.5)

Vectors of different widths cannot be compared and Postgres will not
convert them, so every existing embedding has to go. What must NOT go is
the chunk: `decision_citations.chunk_id` points at it with ON DELETE SET
NULL, so deleting chunks would quietly blank the citations on every
decision already made. The audit trail is the product; it does not get
damaged by a model upgrade.

So `embedding` becomes nullable and the vectors are cleared, keeping every
chunk's text and every citation's target. A chunk with no vector is invisible
to vector search and still found by FTS, which is a degraded state rather
than a broken one, and it is visible: `scripts/reembed.py --status` counts
them.

Re-embed after running this: `uv run python scripts/reembed.py`.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-07
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

OLD_DIMENSIONS = 1536
NEW_DIMENSIONS = 1024


def _resize(dimensions: int) -> None:
    # The HNSW index is built for a specific width; drop, resize, rebuild.
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding DROP NOT NULL")
    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.execute(
        f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({dimensions})"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def upgrade() -> None:
    _resize(NEW_DIMENSIONS)


def downgrade() -> None:
    _resize(OLD_DIMENSIONS)
