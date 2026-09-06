"""Agent dependencies: what tools can reach during a run."""

import uuid
from dataclasses import dataclass

from app.grounding.turn_registry import TurnRegistry


@dataclass
class AgentDeps:
    user_id: uuid.UUID
    registry: TurnRegistry
