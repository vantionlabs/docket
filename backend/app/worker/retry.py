"""Retry backoff — pure, unit-testable."""

from app.config import settings


def backoff_seconds(attempt: int) -> int:
    """Exponential backoff for a given (1-based) attempt number.

    delay = base * 2^(attempt-1), capped at the configured max.
    attempt 1 -> base, 2 -> 2*base, 3 -> 4*base, ...
    """
    base = settings.event_retry_base_delay_seconds
    delay = base * (2 ** max(0, attempt - 1))
    return min(delay, settings.event_retry_max_delay_seconds)
