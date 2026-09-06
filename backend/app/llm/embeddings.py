"""Embeddings, provider-agnostic.

Anthropic has no embeddings API, so this is chosen independently of the chat
provider (`EMBEDDING_PROVIDER`). openai and azure use the OpenAI SDK
(`OpenAI` vs `AzureOpenAI`); add a branch here for Voyage/Cohere/local.
Output dimension is fixed by settings, so it always matches the pgvector
column. Every call records usage/cost.
"""

from functools import lru_cache
from typing import Any

from app.config import settings

_BATCH_SIZE = 128


@lru_cache
def _client() -> Any:
    provider = settings.embedding_provider.lower()
    if provider == "openai":
        from openai import OpenAI

        return OpenAI(api_key=settings.openai_api_key)
    if provider == "azure":
        from openai import AzureOpenAI

        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER {settings.embedding_provider!r} (openai|azure)")


def embed_query(text: str) -> list[float]:
    return embed_batch([text])[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    from app.observability.usage import record_usage

    vectors: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        response = _client().embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
        )
        vectors.extend(item.embedding for item in response.data)
        if response.usage:
            record_usage(
                operation="embedding",
                model=settings.embedding_model,
                input_tokens=response.usage.total_tokens,
            )
    return vectors
