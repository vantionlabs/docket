"""Hybrid retrieval: vector search + full-text search, fused with RRF.

The two searches run in parallel threads on separate sessions, results are
combined with Reciprocal Rank Fusion (k from settings), and the top-k
chunks are hydrated together with their ±radius neighbors (by chunk_index)
so the agent sees enough surrounding context to ground an answer.

Every query filters on user_id: retrieval never crosses user boundaries.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy import text

from app.config import settings
from app.db.engine import SessionLocal
from app.retrieval.embeddings import embed_query


@dataclass
class RetrievedChunk:
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    filename: str
    is_neighbor: bool = False


def _vector_search(user_id: uuid.UUID, query_embedding: list[float], k: int) -> list[uuid.UUID]:
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT id FROM document_chunks "
                "WHERE user_id = :user_id "
                "ORDER BY embedding <=> CAST(:embedding AS vector) "
                "LIMIT :k"
            ),
            {"user_id": user_id, "embedding": str(query_embedding), "k": k},
        ).fetchall()
        return [row.id for row in rows]


def _fts_search(user_id: uuid.UUID, query: str, k: int) -> list[uuid.UUID]:
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT id FROM document_chunks "
                "WHERE user_id = :user_id "
                "AND fts @@ plainto_tsquery(:config, :query) "
                "ORDER BY ts_rank_cd(fts, plainto_tsquery(:config, :query)) DESC "
                "LIMIT :k"
            ),
            {
                "user_id": user_id,
                "query": query,
                "k": k,
                "config": settings.retrieval_fts_config,
            },
        ).fetchall()
        return [row.id for row in rows]


def rrf_fuse(rankings: list[list[uuid.UUID]], k: int) -> list[uuid.UUID]:
    """Reciprocal Rank Fusion: score(d) = sum over rankings of 1/(k + rank)."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda cid: scores[cid], reverse=True)


def _hydrate(user_id: uuid.UUID, chunk_ids: list[uuid.UUID], radius: int) -> list[RetrievedChunk]:
    if not chunk_ids:
        return []
    with SessionLocal() as db:
        primary = db.execute(
            text(
                "SELECT c.id, c.document_id, c.chunk_index, c.content, d.filename "
                "FROM document_chunks c JOIN source_documents d ON d.id = c.document_id "
                "WHERE c.id = ANY(:ids) AND c.user_id = :user_id"
            ),
            {"ids": chunk_ids, "user_id": user_id},
        ).fetchall()

        chunks = {
            row.id: RetrievedChunk(
                id=row.id,
                document_id=row.document_id,
                chunk_index=row.chunk_index,
                content=row.content,
                filename=row.filename,
            )
            for row in primary
        }

        if radius > 0 and primary:
            neighbor_rows = db.execute(
                text(
                    "SELECT c.id, c.document_id, c.chunk_index, c.content, d.filename "
                    "FROM document_chunks c "
                    "JOIN source_documents d ON d.id = c.document_id "
                    "JOIN document_chunks p ON p.document_id = c.document_id "
                    "WHERE p.id = ANY(:ids) AND c.user_id = :user_id "
                    "AND abs(c.chunk_index - p.chunk_index) <= :radius AND c.id != p.id"
                ),
                {"ids": chunk_ids, "user_id": user_id, "radius": radius},
            ).fetchall()
            for row in neighbor_rows:
                if row.id not in chunks:
                    chunks[row.id] = RetrievedChunk(
                        id=row.id,
                        document_id=row.document_id,
                        chunk_index=row.chunk_index,
                        content=row.content,
                        filename=row.filename,
                        is_neighbor=True,
                    )

    # Primary chunks keep fused order; neighbors follow, grouped by document.
    ordered = [chunks[cid] for cid in chunk_ids if cid in chunks]
    neighbors = sorted(
        (c for c in chunks.values() if c.is_neighbor),
        key=lambda c: (str(c.document_id), c.chunk_index),
    )
    return ordered + neighbors


def hybrid_search(user_id: uuid.UUID, query: str) -> list[RetrievedChunk]:
    candidate_k = settings.retrieval_candidate_k
    with ThreadPoolExecutor(max_workers=2) as pool:
        embedding_future = pool.submit(embed_query, query)
        fts_future = pool.submit(_fts_search, user_id, query, candidate_k)
        vector_ids = _vector_search(user_id, embedding_future.result(), candidate_k)
        fts_ids = fts_future.result()

    fused = rrf_fuse([vector_ids, fts_ids], k=settings.retrieval_rrf_k)
    top_k = settings.retrieval_top_k
    radius = settings.retrieval_neighbor_radius

    if not settings.rerank_enabled:
        return _hydrate(user_id, fused[:top_k], radius)

    # Rerank: hydrate a wider candidate pool (no neighbors), reorder by
    # relevance to the query, keep top_k, then expand neighbors for those.
    from app.retrieval.rerank import rerank

    candidates = _hydrate(user_id, fused[: settings.rerank_candidates], radius=0)
    best = rerank(query, candidates, top_k)
    return _hydrate(user_id, [c.id for c in best], radius)
