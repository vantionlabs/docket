"""Agent tools: bounded document access, recorded into the TurnRegistry.

Tools are the only door between the model and the corpus. Everything they
return is recorded in the registry so the grounding validator can verify
that every citation points at something actually retrieved this turn.
"""

import uuid

from pydantic_ai import RunContext

from app.agent.deps import AgentDeps
from app.retrieval.hybrid import hybrid_search


def search_documents(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the user's documents. Returns the most relevant passages with
    their chunk ids; cite chunks by these ids."""
    chunks = hybrid_search(ctx.deps.user_id, query)
    ctx.deps.registry.record(chunks)
    if not chunks:
        return "No matching passages found."
    blocks = [
        f"[chunk_id: {c.id}] (source: {c.filename}, section {c.chunk_index})\n{c.content}"
        for c in chunks
    ]
    return "\n\n---\n\n".join(blocks)


def read_chunk(ctx: RunContext[AgentDeps], chunk_id: str) -> str:
    """Re-read the full text of a chunk already surfaced this turn."""
    try:
        cid = uuid.UUID(chunk_id)
    except ValueError:
        return "Invalid chunk id."
    chunk = ctx.deps.registry.get(cid)
    if chunk is None:
        return "Unknown chunk id; only chunks returned by search_documents can be read."
    return f"[chunk_id: {chunk.id}] (source: {chunk.filename})\n{chunk.content}"
