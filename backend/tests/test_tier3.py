"""Fast-lane tests for Tier-3 units (no network)."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.retrieval.hybrid import RetrievedChunk


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        content=text,
        filename="d.md",
    )


# --- provider resolution ---
def test_provider_openai_builds(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-x")
    from app.llm import providers

    providers.chat_model.cache_clear()
    model = providers._build("gpt-4.1")
    assert model.model_name == "gpt-4.1"


def test_provider_anthropic_builds(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-x")
    from app.llm import providers

    model = providers._build("claude-sonnet-4-0")
    assert model.model_name == "claude-sonnet-4-0"


def test_provider_unknown_raises(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "nope")
    from app.llm import providers

    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        providers._build("x")


# --- reranking ---
def test_rerank_disabled_truncates(monkeypatch):
    from app.config import settings
    from app.retrieval import rerank as rr

    monkeypatch.setattr(settings, "rerank_enabled", False)
    chunks = [_chunk("a"), _chunk("b"), _chunk("c")]
    assert rr.rerank("q", chunks, top_k=2) == chunks[:2]


def test_rerank_reorders_by_score(monkeypatch):
    from app.config import settings
    from app.retrieval import rerank as rr

    monkeypatch.setattr(settings, "rerank_enabled", True)
    chunks = [_chunk("a"), _chunk("b"), _chunk("c")]

    # Model ranks index 2 highest, then 0, then 1.
    fake = MagicMock()
    fake.output.scores = [
        rr._Score(index=0, relevance=5),
        rr._Score(index=1, relevance=1),
        rr._Score(index=2, relevance=9),
    ]
    with patch.object(rr, "_reranker") as agent:
        agent.return_value.run_sync.return_value = fake
        out = rr.rerank("q", chunks, top_k=2)
    assert out == [chunks[2], chunks[0]]


def test_rerank_falls_back_on_error(monkeypatch):
    from app.config import settings
    from app.retrieval import rerank as rr

    monkeypatch.setattr(settings, "rerank_enabled", True)
    chunks = [_chunk("a"), _chunk("b")]
    with patch.object(rr, "_reranker", side_effect=RuntimeError("boom")):
        assert rr.rerank("q", chunks, top_k=1) == chunks[:1]
