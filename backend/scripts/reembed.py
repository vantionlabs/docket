"""Re-embed chunks that have no vector.

Needed after an embedding-model change (migration 0006 cleared every
vector when the width moved from 1536 to 1024), and useful whenever
ingestion was run without an embedding provider configured.

    uv run python scripts/reembed.py --status      # count what is missing
    uv run python scripts/reembed.py               # embed it
    uv run python scripts/reembed.py --contextual  # embed with clause context

A chunk with no vector is invisible to vector search and still found by
FTS. That is a degraded corpus rather than a broken one, which is exactly
the kind of state that goes unnoticed, so `--status` exists to make it
countable rather than something you discover from bad answers.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.engine import SessionLocal  # noqa: E402
from app.db.models import DocumentChunk, SourceDocument  # noqa: E402
from app.llm.embeddings import embed_documents  # noqa: E402

BATCH = 64


def status(db) -> tuple[int, int]:
    total = db.scalar(select(func.count()).select_from(DocumentChunk)) or 0
    missing = (
        db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.embedding.is_(None)
            )
        )
        or 0
    )
    return total, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="report and exit")
    parser.add_argument(
        "--contextual",
        action="store_true",
        help="prepend document and section context before embedding (see app/ingestion/context.py)",
    )
    parser.add_argument("--all", action="store_true", help="re-embed every chunk, not just unset")
    args = parser.parse_args()

    with SessionLocal() as db:
        total, missing = status(db)
        print(
            f"{total} chunks, {missing} without a vector "
            f"({settings.embedding_provider}/{settings.embedding_model}, "
            f"{settings.embedding_dimensions}d)"
        )
        if args.status:
            return 0

        stmt = select(DocumentChunk).order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        if not args.all:
            stmt = stmt.where(DocumentChunk.embedding.is_(None))
        chunks = list(db.scalars(stmt))
        if not chunks:
            print("nothing to do")
            return 0

        filenames = {
            row.id: row.filename
            for row in db.execute(
                select(SourceDocument.id, SourceDocument.filename).where(
                    SourceDocument.id.in_({c.document_id for c in chunks})
                )
            )
        }

        # Reassemble each document from its chunks: the heading path needs
        # the surrounding text, and re-fetching from R2 here would make a
        # local re-embed depend on object storage.
        full_text: dict = {}
        for chunk in sorted(chunks, key=lambda c: (str(c.document_id), c.chunk_index)):
            full_text.setdefault(chunk.document_id, "")
            full_text[chunk.document_id] += chunk.content + "\n\n"

        done = 0
        for start in range(0, len(chunks), BATCH):
            batch = chunks[start : start + BATCH]
            if args.contextual:
                from app.ingestion.context import contextualize

                texts = [
                    contextualize(
                        c.content,
                        filenames.get(c.document_id, ""),
                        document_text=full_text.get(c.document_id, ""),
                    )
                    for c in batch
                ]
            else:
                texts = [c.content for c in batch]

            for chunk, vector in zip(batch, embed_documents(texts), strict=True):
                chunk.embedding = vector
            db.commit()
            done += len(batch)
            print(f"  embedded {done}/{len(chunks)}")

        total, missing = status(db)
        print(f"done: {total} chunks, {missing} without a vector")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
