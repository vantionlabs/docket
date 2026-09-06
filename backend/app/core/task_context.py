"""TaskContext: the data that flows through a workflow.

The Launchpad pattern in one line: workflows execute nodes that pass data
through a TaskContext. The context carries the triggering event's payload,
accumulates each node's output under the node's name, and holds shared
metadata (db session, user id) that nodes may need.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session


@dataclass
class TaskContext:
    event_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    user_id: str | None
    db: Session
    # Each node stores its output here under its class name, so downstream
    # nodes (and the event's `result`) can read what earlier nodes produced.
    nodes: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def output_of(self, node_name: str) -> Any:
        return self.nodes.get(node_name)

    def to_result(self) -> dict[str, Any]:
        """JSON-safe summary stored on the event row when the workflow ends."""
        summary: dict[str, Any] = {}
        for name, value in self.nodes.items():
            try:
                import json

                json.dumps(value)
                summary[name] = value
            except (TypeError, ValueError):
                summary[name] = str(value)
        return summary
