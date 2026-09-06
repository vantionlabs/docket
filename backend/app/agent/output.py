"""The agent's structured output: a grounded answer with citations."""

from pydantic import BaseModel, Field


class AgentCitation(BaseModel):
    index: int = Field(description="1-based citation number matching a [n] marker in the answer")
    chunk_id: str = Field(description="The id of the retrieved chunk this citation quotes")
    excerpt: str = Field(description="A short verbatim excerpt from the chunk supporting the claim")


class GroundedAnswer(BaseModel):
    answer: str = Field(
        description="The answer, with [n] markers referencing the citations list"
    )
    citations: list[AgentCitation] = Field(default_factory=list)
    insufficient_evidence: bool = Field(
        default=False,
        description="True when the retrieved documents cannot support an answer",
    )
