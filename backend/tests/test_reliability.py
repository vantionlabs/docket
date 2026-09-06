"""Fast-lane tests for the Tier-1 reliability pieces (no broker, no DB)."""

import hashlib
import hmac

import pytest

from app.security.webhooks import verify_signature
from app.worker.retry import backoff_seconds


# --- retry backoff ---
def test_backoff_is_exponential():
    b = backoff_seconds
    # base=10 by default: 10, 20, 40, 80, ...
    assert b(1) == 10
    assert b(2) == 20
    assert b(3) == 40


def test_backoff_is_capped():
    assert backoff_seconds(50) <= 600  # event_retry_max_delay_seconds


def test_backoff_never_negative():
    assert backoff_seconds(0) >= 0


# --- webhook signature ---
def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_signing_secret", "s3cret")
    body = b'{"hello":"world"}'
    assert verify_signature(body, _sign(body, "s3cret")) is True


def test_wrong_secret_fails(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_signing_secret", "s3cret")
    body = b'{"hello":"world"}'
    assert verify_signature(body, _sign(body, "wrong")) is False


def test_tampered_body_fails(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_signing_secret", "s3cret")
    sig = _sign(b'{"amount":10}', "s3cret")
    assert verify_signature(b'{"amount":9999}', sig) is False


def test_missing_secret_or_header_fails_closed(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_signing_secret", "")
    assert verify_signature(b"x", "sha256=abc") is False
    monkeypatch.setattr(settings, "webhook_signing_secret", "s3cret")
    assert verify_signature(b"x", None) is False


@pytest.mark.parametrize("prefix", ["sha256=", ""])
def test_signature_prefix_optional(monkeypatch, prefix):
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_signing_secret", "s3cret")
    body = b"payload"
    digest = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, prefix + digest) is True
