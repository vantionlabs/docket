"""Webhook signature verification (HMAC-SHA256 over the raw body).

This covers the common scheme: `signature = hex(hmac_sha256(secret, body))`,
sent as `sha256=<hex>`. Providers with bespoke schemes (Stripe's timestamped
`t=,v1=`, etc.) verify differently — add a per-source verifier and branch on
the `{source}` path segment when you integrate one.
"""

import hashlib
import hmac

from app.config import settings


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Constant-time-compare the provided signature against one computed from
    the raw body and the configured secret. Rejects when either the secret or
    the header is missing (fail closed)."""
    secret = settings.webhook_signing_secret
    if not secret or not signature_header:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, provided)
