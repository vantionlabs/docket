"""Transactional email via Resend (REST, over httpx — no extra SDK).

No-op (logs the intended send) when RESEND_API_KEY is unset, so local dev and
tests never send real mail. Used for password reset + email verification, and
available for any notification workflow.
"""

import httpx

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


def send_email(*, to: str, subject: str, html: str) -> bool:
    """Send an email. Returns True if dispatched, False if skipped/failed."""
    if not settings.resend_api_key:
        log.info("email.skipped", to=to, subject=subject, reason="no RESEND_API_KEY")
        return False
    try:
        resp = httpx.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("email.sent", to=to, subject=subject)
        return True
    except Exception:  # noqa: BLE001 — email failures shouldn't break the request
        log.exception("email.failed", to=to, subject=subject)
        return False
