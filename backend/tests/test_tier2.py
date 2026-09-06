"""Fast-lane tests for Tier-2 units (no DB, no network)."""

from app.auth.api_keys import _hash, generate_key
from app.observability.usage import cost_usd


# --- API key generation ---
def test_generate_key_shape():
    plaintext, key_hash, prefix = generate_key()
    assert plaintext.startswith("sk_")
    assert key_hash == _hash(plaintext)
    assert prefix.startswith("sk_") and len(prefix) < len(plaintext)


def test_key_hash_is_deterministic_and_not_plaintext():
    plaintext, key_hash, _ = generate_key()
    assert key_hash != plaintext
    assert _hash(plaintext) == key_hash
    assert len(key_hash) == 64  # sha256 hex


def test_keys_are_unique():
    assert generate_key()[0] != generate_key()[0]


# --- cost computation ---
def test_known_model_cost():
    # gpt-4.1: (2.00, 8.00) per 1M
    c = cost_usd("gpt-4.1", input_tokens=1_000_000, output_tokens=1_000_000)
    assert round(c, 4) == 10.0


def test_provider_prefix_stripped():
    assert cost_usd("openai:gpt-4.1", 1_000_000, 0) == 2.0


def test_unknown_model_costs_zero():
    assert cost_usd("some-future-model", 1_000_000, 1_000_000) == 0.0


def test_embedding_cost_input_only():
    # text-embedding-3-small: (0.02, 0.0)
    assert round(cost_usd("text-embedding-3-small", 1_000_000, 0), 4) == 0.02
