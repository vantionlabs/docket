"""System-of-record adapters: the one place Docket touches the outside world."""

from app.adapters.base import (
    Adapter,
    AdapterRequest,
    AdapterResponse,
    DryRunAdapter,
    get_adapter,
    register_adapter,
)

__all__ = [
    "Adapter",
    "AdapterRequest",
    "AdapterResponse",
    "DryRunAdapter",
    "get_adapter",
    "register_adapter",
]
