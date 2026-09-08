"""Cost logging has to know the models this project runs on.

Every model in use was missing from PRICES, so `cost_usd` returned zero for
every call and the spend log was silently useless for the whole build. It
never failed; it just logged nothing worth reading.
"""

import pytest

from app.config import settings
from app.observability.usage import PRICES, cost_usd


@pytest.mark.parametrize(
    "setting", ["chat_model", "grounding_model", "embedding_model"]
)
def test_the_configured_models_are_priced(setting):
    """The test that would have caught it: whatever config points at must
    have a row here, or its calls log zero."""
    model = getattr(settings, setting)
    assert cost_usd(model, 1_000_000, 0) > 0, f"{setting}={model!r} is not in PRICES"


def test_a_dated_snapshot_prices_as_its_base_model():
    """`claude-haiku-4-5-20251001` costs what `claude-haiku-4-5` costs. A
    table with a row per snapshot date would go stale on every release."""
    assert cost_usd("claude-haiku-4-5-20251001", 1_000_000, 1_000_000) == cost_usd(
        "claude-haiku-4-5", 1_000_000, 1_000_000
    )


def test_a_provider_prefix_is_stripped():
    assert cost_usd("anthropic:claude-sonnet-5", 1_000_000, 0) == 2.00


def test_embeddings_bill_input_only():
    """An embedding call returns vectors, not tokens: charging for output
    would inflate every ingestion run."""
    assert cost_usd("voyage-3.5", 1_000_000, 999_999) == pytest.approx(0.06)


def test_an_unknown_model_is_free_rather_than_guessed():
    """Better a zero somebody notices than a number nobody can trust."""
    assert cost_usd("some-model-we-do-not-price", 1_000_000, 1_000_000) == 0.0


def test_prices_are_input_output_pairs():
    for model, price in PRICES.items():
        assert len(price) == 2, model
        assert price[0] >= 0 and price[1] >= 0, model


# --- routing through OpenRouter ------------------------------------------


def test_an_openrouter_id_prices_as_the_underlying_model():
    """OpenRouter ids carry a vendor prefix. Without stripping it, every
    call through OpenRouter would log zero, which is the same silent hole
    the Claude models were in."""
    assert cost_usd("anthropic/claude-sonnet-5", 1_000_000, 0) == cost_usd(
        "claude-sonnet-5", 1_000_000, 0
    )
    assert cost_usd("openai/gpt-4o", 1_000_000, 0) == cost_usd("gpt-4o", 1_000_000, 0)


def test_a_prefixed_dated_snapshot_still_resolves():
    assert cost_usd("anthropic/claude-haiku-4-5-20251001", 1_000_000, 0) == cost_usd(
        "claude-haiku-4-5", 1_000_000, 0
    )


def test_an_unpriced_openrouter_model_is_still_zero_not_a_guess():
    """A model nobody has priced logs zero and says so, rather than
    borrowing a number from a model that happens to sound similar."""
    assert cost_usd("somevendor/some-model", 1_000_000, 0) == 0.0
