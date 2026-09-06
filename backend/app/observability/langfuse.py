"""Optional Langfuse tracing.

When LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are unset (or the langfuse
extra isn't installed) everything here is a silent no-op, so app code can
call `observe_span(...)` unconditionally.
"""

from contextlib import contextmanager
from typing import Any

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)

_client: Any | None = None
_checked = False


def _get_client() -> Any | None:
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except ImportError:
        log.warning("langfuse keys set but package missing: uv sync --extra langfuse")
    return _client


@contextmanager
def observe_span(name: str, **attributes: Any):
    """Trace a span when Langfuse is configured; otherwise do nothing."""
    client = _get_client()
    if client is None:
        yield None
        return
    span = client.span(name=name, metadata=attributes or None)
    try:
        yield span
    finally:
        span.end()
