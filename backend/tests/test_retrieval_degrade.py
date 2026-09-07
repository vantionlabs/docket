"""Retrieval without an embedding provider (the bug that broke chat).

Switching the default embedding provider to Voyage with no key set made
`embed_query` raise, and chat's retrieval died on it: the stream stalled at
"analyzing" and never recovered. A lexical answer with citations beats a
500, so retrieval degrades. What it must not do is degrade quietly.
"""

import pytest

from app.llm.embeddings import embeddings_available


def _settings(monkeypatch, **values):
    from app.config import settings

    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)
    return settings


def test_none_is_a_supported_deliberate_setting(monkeypatch):
    """Running without an embedding bill should be a decision, not a crash
    somebody worked around."""
    _settings(monkeypatch, embedding_provider="none")
    available, reason = embeddings_available()
    assert not available
    assert "FTS" in reason


@pytest.mark.parametrize(
    ("provider", "key_field"),
    [("voyage", "voyage_api_key"), ("openai", "openai_api_key")],
)
def test_a_configured_provider_with_no_key_is_unavailable(monkeypatch, provider, key_field):
    _settings(monkeypatch, embedding_provider=provider, **{key_field: ""})
    available, reason = embeddings_available()
    assert not available
    assert "unset" in reason


@pytest.mark.parametrize(
    ("provider", "key_field"),
    [("voyage", "voyage_api_key"), ("openai", "openai_api_key")],
)
def test_a_configured_provider_with_a_key_is_available(monkeypatch, provider, key_field):
    _settings(monkeypatch, embedding_provider=provider, **{key_field: "sk-test"})
    available, reason = embeddings_available()
    assert available
    assert reason == ""


def test_an_unknown_provider_is_unavailable_not_an_exception(monkeypatch):
    """A typo in config should degrade retrieval, not take the app down."""
    _settings(monkeypatch, embedding_provider="voyaeg")
    available, reason = embeddings_available()
    assert not available
    assert "Unknown" in reason


def test_degrading_is_logged_every_time(monkeypatch, capsys):
    """The thing this codebase keeps getting bitten by is retrieval that
    silently got worse. It has to be said out loud on every search, not
    once per process, or a long-running worker degrades in silence.

    Asserted against stdout rather than caplog: structlog writes there
    directly and never reaches pytest's logging handler.
    """
    import uuid

    from app.retrieval import hybrid

    _settings(monkeypatch, embedding_provider="none")
    monkeypatch.setattr(hybrid, "_fts_search", lambda *a, **k: [])
    monkeypatch.setattr(hybrid, "_hydrate", lambda *a, **k: [])

    hybrid.hybrid_search(uuid.uuid4(), "anything")
    hybrid.hybrid_search(uuid.uuid4(), "anything else")

    assert capsys.readouterr().out.count("retrieval.degraded") == 2


def test_fts_only_still_returns_results(monkeypatch):
    """Degraded is not broken: the lexical half still ranks."""
    import uuid

    from app.retrieval import hybrid

    _settings(monkeypatch, embedding_provider="none")
    ids = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(hybrid, "_fts_search", lambda *a, **k: ids)
    monkeypatch.setattr(hybrid, "_hydrate", lambda _u, chunk_ids, *a, **k: list(chunk_ids))

    assert hybrid.hybrid_search(uuid.uuid4(), "threshold") == ids


def test_a_provider_outage_mid_search_degrades_rather_than_500s(monkeypatch):
    """A key that exists but a provider that is down is the same problem."""
    import uuid

    from app.retrieval import hybrid

    _settings(monkeypatch, embedding_provider="voyage", voyage_api_key="sk-test")

    def _boom(_text):
        raise RuntimeError("voyage timed out")

    monkeypatch.setattr(hybrid, "embed_query", _boom)
    monkeypatch.setattr(hybrid, "_fts_search", lambda *a, **k: [])
    monkeypatch.setattr(hybrid, "_hydrate", lambda *a, **k: [])

    assert hybrid.hybrid_search(uuid.uuid4(), "anything") == []
