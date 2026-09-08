"""LLM usage + cost logging.

One row per model call (`llm_usage`) with token counts and a computed cost,
so clients get spend visibility and you have the basis for per-user limits or
billing. Prices are USD per 1M tokens — update `PRICES` when rates change or
you add models; unknown models log at cost 0 rather than guessing.
"""

import re
import uuid

from app.db.engine import SessionLocal
from app.db.models import LlmUsage
from app.logging import get_logger

log = get_logger(__name__)

# USD per 1M tokens: (input, output). Keep current; unknown → (0, 0).
#
# Every model this project actually uses was missing from here, so every
# call logged a cost of zero and the spend log was quietly useless for the
# whole build. If you change CHAT_MODEL, GROUNDING_MODEL or EMBEDDING_MODEL,
# add the model here in the same commit.
PRICES: dict[str, tuple[float, float]] = {
    # Anthropic, the models this project runs on.
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    # Voyage embeddings. Output is free: embedding calls return vectors,
    # not tokens, so only the input side is ever billed.
    "voyage-3.5": (0.06, 0.0),
    "voyage-3.5-lite": (0.02, 0.0),
    # OpenAI / Azure, for deployments that use them.
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    key = model.split(":", 1)[-1]  # strip a "openai:" / "anthropic:" prefix
    if key not in PRICES:
        # OpenRouter ids carry a vendor prefix: `anthropic/claude-sonnet-5`.
        # Strip it and price as the underlying model.
        #
        # This is an ESTIMATE when routing through OpenRouter, which bills
        # its own rates with a margin and can vary by route. Their dashboard
        # is authoritative for what you actually pay; this exists so the
        # relative cost of operations inside the app stays visible, which is
        # what the log is for.
        key = key.rsplit("/", 1)[-1]
    if key not in PRICES:
        # OpenRouter writes versions with dots (`claude-haiku-4.5`) where the
        # first-party id uses dashes. Same model, same price.
        key = key.replace(".", "-")
    if key not in PRICES:
        # A dated snapshot like `claude-haiku-4-5-20251001` prices the same
        # as the model it pins. Falling back to the base id beats logging
        # zero and beats a table that needs a row per snapshot date.
        key = _undated(key)
    in_price, out_price = PRICES.get(key, (0.0, 0.0))
    if key not in PRICES:
        log.warning("usage.unknown_model", model=model)
    return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price


def _undated(model: str) -> str:
    """Strip a trailing -YYYYMMDD snapshot suffix, if there is one."""
    match = re.fullmatch(r"(.+)-\d{8}", model)
    return match.group(1) if match else model


def record_run_usage(
    result: object,
    *,
    operation: str,
    model: str,
    user_id: uuid.UUID | None = None,
) -> None:
    """Record token usage from a pydantic-ai run result.

    One helper for every call site, because there were six of them and they
    were all wrong in the same way: `result.usage` is a PROPERTY in current
    pydantic-ai, not a method, so `result.usage()` raised TypeError. Each
    site wrapped that in `except Exception: pass`, so no Anthropic call in
    this project ever logged a single token. It never failed; it just
    silently recorded nothing.

    Handles both shapes, because the SDK has had both, and logs rather than
    swallowing when neither works. Usage logging still must not break the
    request it measures, but "must not break" is not the same as "must not
    say anything".
    """
    try:
        usage = result.usage
        if callable(usage):  # older pydantic-ai exposed a method
            usage = usage()
        record_usage(
            operation=operation,
            model=model,
            input_tokens=getattr(usage, "input_tokens", None)
            or getattr(usage, "request_tokens", 0)
            or 0,
            output_tokens=getattr(usage, "output_tokens", None)
            or getattr(usage, "response_tokens", 0)
            or 0,
            user_id=user_id,
        )
    except Exception:  # noqa: BLE001 -- never break the caller over accounting
        log.exception("usage.extract_failed", operation=operation, model=model)


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
