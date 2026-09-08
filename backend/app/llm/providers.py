"""LLM provider construction — the one place model+provider is resolved.

Every model call in the app goes through these two builders, so switching
provider is a config change (`LLM_PROVIDER` + `CHAT_MODEL`), never a code
change. Keys are passed explicitly from settings (not read from os.environ),
so `.env` alone is enough.

  - openai      → OpenAIChatModel + OpenAIProvider(OPENAI_API_KEY)
  - anthropic   → AnthropicModel + AnthropicProvider(ANTHROPIC_API_KEY)
  - azure       → OpenAIChatModel + AzureProvider(AZURE_OPENAI_*)
  - openrouter  → OpenAIChatModel + OpenRouterProvider(OPENROUTER_API_KEY)

**OpenRouter reaches many vendors through one key**, with model ids like
`anthropic/claude-sonnet-5` or `openai/gpt-5`. Two things are worth knowing
before pointing this app at an arbitrary one.

This pipeline does not just generate prose. Extraction returns a typed model
with a verbatim span per field, decisions return a closed enum with
citations, and the judge returns a structured verdict. All of that leans on
reliable structured output and close instruction-following. A model that
chats well and follows a JSON schema loosely will not merely score worse
here; it will fail validation and every case will escalate. Change the
grounding model and the chat model independently, and re-run the eval after
either.

Embeddings are separate and stay separate (`EMBEDDING_PROVIDER`), because
OpenRouter does not serve them.
"""

from functools import lru_cache
from typing import Any

from app.config import settings


def _build(model_name: str) -> Any:
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=settings.openai_api_key))

    if provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(
            model_name, provider=AnthropicProvider(api_key=settings.anthropic_api_key)
        )

    if provider == "openrouter":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        # The native provider rather than OpenAIProvider with a base_url:
        # it carries per-model profiles, so pydantic-ai knows which models
        # actually support strict structured output rather than assuming
        # every model behaves like an OpenAI one.
        return OpenAIChatModel(
            model_name,
            provider=OpenRouterProvider(
                api_key=settings.openrouter_api_key,
                app_url=settings.frontend_url,
                app_title=settings.otel_service_name,
            ),
        )

    if provider == "azure":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.azure import AzureProvider

        return OpenAIChatModel(
            model_name,
            provider=AzureProvider(
                azure_endpoint=settings.azure_openai_endpoint,
                api_version=settings.azure_openai_api_version,
                api_key=settings.azure_openai_api_key,
            ),
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER {settings.llm_provider!r} "
        "(openai|anthropic|azure|openrouter)"
    )


@lru_cache
def chat_model() -> Any:
    """The agent's generation model."""
    return _build(settings.chat_model)


@lru_cache
def grounding_model() -> Any:
    """The grounding judge's model (usually a cheaper one)."""
    return _build(settings.grounding_model)
