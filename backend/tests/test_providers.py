"""Provider selection: the one seam a model is built through.

Switching provider must stay a config change. These do not call any API;
they check that each provider name resolves to the right client and that an
unknown one fails loudly rather than falling back to a default nobody chose.
"""

import pytest

from app.config import settings
from app.llm import providers


@pytest.fixture(autouse=True)
def _clear_cache():
    providers.chat_model.cache_clear()
    providers.grounding_model.cache_clear()
    yield
    providers.chat_model.cache_clear()
    providers.grounding_model.cache_clear()


def test_anthropic_builds_an_anthropic_model(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    assert type(providers._build("claude-sonnet-5")).__name__ == "AnthropicModel"


def test_openrouter_builds_an_openai_compatible_model(monkeypatch):
    """OpenRouter speaks the OpenAI wire format, so the model class is the
    OpenAI one; what differs is the provider underneath it."""
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")
    model = providers._build("anthropic/claude-sonnet-5")
    assert type(model).__name__ == "OpenAIChatModel"
    assert "openrouter" in type(model._provider).__name__.lower()


def test_openrouter_passes_the_model_id_through_unchanged(monkeypatch):
    """`anthropic/claude-sonnet-5` is the id OpenRouter expects. Rewriting
    it here would route to the wrong model or none at all."""
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")
    model = providers._build("google/gemini-2.5-pro")
    assert model.model_name == "google/gemini-2.5-pro"


def test_an_unknown_provider_fails_loudly(monkeypatch):
    """Never fall back to a default nobody chose: a typo in LLM_PROVIDER
    should stop the app, not quietly bill a different vendor."""
    monkeypatch.setattr(settings, "llm_provider", "openrouterr")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        providers._build("whatever")


def test_the_error_lists_what_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "nope")
    with pytest.raises(ValueError, match="openrouter"):
        providers._build("whatever")


def test_chat_and_grounding_can_be_different_models(monkeypatch):
    """The judge is a separate, usually cheaper model. Changing one must
    not change the other."""
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(settings, "chat_model", "claude-sonnet-5")
    monkeypatch.setattr(settings, "grounding_model", "claude-haiku-4-5")
    assert providers.chat_model().model_name == "claude-sonnet-5"
    assert providers.grounding_model().model_name == "claude-haiku-4-5"
