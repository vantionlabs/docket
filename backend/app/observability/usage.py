"""LLM usage + cost logging.

One row per model call (`llm_usage`) with token counts and a computed cost,
so clients get spend visibility and you have the basis for per-user limits or
billing. Prices are USD per 1M tokens — update `PRICES` when rates change or
you add models; unknown models log at cost 0 rather than guessing.
"""

import uuid

from app.db.engine import SessionLocal
from app.db.models import LlmUsage
from app.logging import get_logger

log = get_logger(__name__)

# USD per 1M tokens: (input, output). Keep current; unknown → (0, 0).
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    # Anthropic / Azure deployments: add the model names you use.
    "claude-sonnet-4": (3.00, 15.00),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    key = model.split(":", 1)[-1]  # strip a "openai:" / "anthropic:" prefix
    in_price, out_price = PRICES.get(key, (0.0, 0.0))
    if key not in PRICES:
        log.warning("usage.unknown_model", model=model)
    return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price


def record_usage(
    *,
    operation: str,
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
    user_id: uuid.UUID | None = None,
) -> None:
    """Persist one usage row. Never raises — usage logging must not break the
    request it is measuring."""
    try:
        with SessionLocal() as db:
            db.add(
                LlmUsage(
                    user_id=user_id,
                    operation=operation,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd(model, input_tokens, output_tokens),
                )
            )
            db.commit()
    except Exception:  # noqa: BLE001
        log.exception("usage.record_failed", operation=operation, model=model)
