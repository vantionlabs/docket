"""WorkflowRegistry: maps event types to workflow classes.

The worker looks up the workflow for an event's `type` here. Register new
workflows with the decorator:

    @register("document.ingest")
    class DocumentIngestWorkflow(Workflow): ...
"""

from collections.abc import Callable

from app.core.workflow import Workflow

_REGISTRY: dict[str, type[Workflow]] = {}


def register(event_type: str) -> Callable[[type[Workflow]], type[Workflow]]:
    def decorator(cls: type[Workflow]) -> type[Workflow]:
        if event_type in _REGISTRY:
            raise ValueError(f"workflow already registered for {event_type!r}")
        _REGISTRY[event_type] = cls
        return cls

    return decorator


def workflow_for(event_type: str) -> type[Workflow]:
    try:
        return _REGISTRY[event_type]
    except KeyError as exc:
        raise KeyError(f"no workflow registered for event type {event_type!r}") from exc


def registered_types() -> list[str]:
    return sorted(_REGISTRY)
