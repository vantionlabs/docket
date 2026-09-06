"""Optional Sentry error tracking. No-op when SENTRY_DSN is unset."""

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


def init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        log.warning("sentry dsn set but package missing: uv sync --extra sentry")
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        # Never ship request bodies / PII to Sentry by default.
        send_default_pii=False,
    )
    log.info("sentry.initialized")
