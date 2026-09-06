"""Embeddings live in app/llm/embeddings (provider-agnostic). Re-exported
here so retrieval keeps a stable import path."""

from app.llm.embeddings import embed_batch, embed_query

__all__ = ["embed_batch", "embed_query"]
