"""Embeddings, provider-agnostic.

Anthropic has no embeddings API, so this is chosen independently of the chat
provider (`EMBEDDING_PROVIDER`). openai and azure use the OpenAI SDK
(`OpenAI` vs `AzureOpenAI`); voyage uses its own HTTP API. Output dimension
is fixed by settings, so it always matches the pgvector column. Every call
records usage/cost.

**Input type matters for retrieval quality.** Voyage (and Cohere) embed a
query and a document differently on purpose: a question and the passage that
answers it are not the same kind of text, and telling the model which one it
is measurably improves retrieval. Providers that do not distinguish ignore
the hint. This is why `embed_query` is not just `embed_batch([text])[0]`.

**`EMBEDDING_PROVIDER=none` is a supported setting**, meaning "this install
has no embeddings, run retrieval on Postgres FTS alone". It exists so that
running without an embedding bill is a decision somebody made rather than a
crash they worked around. `embeddings_available()` reports whether the
configured provider can actually be used, and retrieval asks before trying.
"""

from functools import lru_cache
from typing import Any, Literal

import httpx

from app.config import settings

_BATCH_SIZE = 128
_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"

InputType = Literal["query", "document"]


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
    if provider == "voyage":
        return None  # voyage speaks plain HTTP; no SDK to construct
    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER {settings.embedding_provider!r} "
        "(openai|azure|voyage|none)"
    )


def embeddings_available() -> tuple[bool, str]:
    """Can this install embed? Returns (available, reason when it cannot).

    Checked rather than discovered by exception, because the answer decides
    how retrieval runs and "it threw" is a bad way to learn a deployment has
    no embedding provider.
    """
    provider = settings.embedding_provider.lower()
    if provider == "none":
        return False, "EMBEDDING_PROVIDER is none: retrieval runs on Postgres FTS alone"
    if provider == "voyage" and not settings.voyage_api_key:
        return False, "EMBEDDING_PROVIDER is voyage but VOYAGE_API_KEY is unset"
    if provider == "openai" and not settings.openai_api_key:
        return False, "EMBEDDING_PROVIDER is openai but OPENAI_API_KEY is unset"
    if provider == "azure" and not settings.azure_openai_api_key:
        return False, "EMBEDDING_PROVIDER is azure but AZURE_OPENAI_API_KEY is unset"
    if provider not in ("openai", "azure", "voyage"):
        return False, f"Unknown EMBEDDING_PROVIDER {settings.embedding_provider!r}"
    return True, ""


def embed_query(text: str) -> list[float]:
    """Embed a search query. Not the same operation as embedding a passage."""
    return embed_batch([text], input_type="query")[0]


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed passages to be retrieved later."""
    return embed_batch(texts, input_type="document")


def embed_batch(texts: list[str], input_type: InputType = "document") -> list[list[float]]:
    from app.observability.usage import record_usage

    if not texts:
        return []

    vectors: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        if settings.embedding_provider.lower() == "voyage":
            batch_vectors, tokens = _voyage_embed(batch, input_type)
        else:
            batch_vectors, tokens = _openai_embed(batch)
        vectors.extend(batch_vectors)
        if tokens:
            record_usage(
                operation="embedding",
                model=settings.embedding_model,
                input_tokens=tokens,
            )
    return vectors


def _openai_embed(batch: list[str]) -> tuple[list[list[float]], int]:
    response = _client().embeddings.create(
        model=settings.embedding_model,
        input=batch,
        dimensions=settings.embedding_dimensions,
    )
    return (
        [item.embedding for item in response.data],
        response.usage.total_tokens if response.usage else 0,
    )


def _voyage_embed(batch: list[str], input_type: InputType) -> tuple[list[list[float]], int]:
    """Voyage's HTTP API. No SDK, in the spirit of the Resend client.

    `output_dimension` is sent explicitly rather than trusting the model
    default, because the pgvector column has a fixed width and a provider
    changing its default would otherwise fail at insert time with a shape
    error nobody would connect to a model upgrade.
    """
    if not settings.voyage_api_key:
        raise ValueError("EMBEDDING_PROVIDER is voyage but VOYAGE_API_KEY is unset")

    response = httpx.post(
        _VOYAGE_URL,
        headers={"Authorization": f"Bearer {settings.voyage_api_key}"},
        json={
            "input": batch,
            "model": settings.embedding_model,
            "input_type": input_type,
            "output_dimension": settings.embedding_dimensions,
        },
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    # Voyage does not promise ordered results; index is authoritative.
    ordered = sorted(body["data"], key=lambda item: item["index"])
    return (
        [item["embedding"] for item in ordered],
        int(body.get("usage", {}).get("total_tokens", 0)),
    )
