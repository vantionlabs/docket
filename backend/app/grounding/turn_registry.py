"""TurnRegistry: the allowlist of chunks surfaced during one chat turn.

Every chunk the agent's tools return is recorded here. The grounding
validator only accepts citations whose chunk id is in the registry, so
the model can never cite something it did not actually retrieve this turn.
"""

import uuid
from dataclasses import dataclass, field

from app.retrieval.hybrid import RetrievedChunk


@dataclass
class TurnRegistry:
    chunks: dict[uuid.UUID, RetrievedChunk] = field(default_factory=dict)

    def record(self, retrieved: list[RetrievedChunk]) -> None:
        for chunk in retrieved:
            self.chunks[chunk.id] = chunk

    def get(self, chunk_id: uuid.UUID) -> RetrievedChunk | None:
        return self.chunks.get(chunk_id)

    def __contains__(self, chunk_id: uuid.UUID) -> bool:
        return chunk_id in self.chunks
