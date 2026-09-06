"""LLM provider construction — the one place model+provider is resolved.

Both the agent and the grounding judge use these builders, so switching
provider is a config change (`LLM_PROVIDER` + `CHAT_MODEL`), never a code
change. Keys are passed explicitly from settings (not read from os.environ),
so `.env` alone is enough.

  - openai     → OpenAIChatModel + OpenAIProvider(OPENAI_API_KEY)
  - anthropic  → AnthropicModel + AnthropicProvider(ANTHROPIC_API_KEY)   # Claude
  - azure      → OpenAIChatModel + AzureProvider(AZURE_OPENAI_*)
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

    raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r} (openai|anthropic|azure)")


@lru_cache
def chat_model() -> Any:
    """The agent's generation model."""
    return _build(settings.chat_model)


@lru_cache
def grounding_model() -> Any:
    """The grounding judge's model (usually a cheaper one)."""
    return _build(settings.grounding_model)
