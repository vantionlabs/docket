"""What a decision is (spec section 9).

The outcome is a closed enum. A model that can invent an outcome can
invent an outcome nobody has a process for, so it picks from four and
nothing else.

Citations are mandatory and they point at policy clauses, not at the
document being decided. The rationale carries [n] markers into them, the
same shape the template's chat answers use, so the same structural check
applies.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Outcome(StrEnum):
    auto_approve = "auto_approve"
    route_for_approval = "route_for_approval"
    reject = "reject"
    needs_human = "needs_human"


class PolicyCitation(BaseModel):
    index: int = Field(
        description="1-based citation number matching an [n] marker in the rationale"
    )
    clause_id: str = Field(description="The id of the policy clause being cited")
    excerpt: str = Field(
        description=(
            "A short verbatim excerpt from that clause, copied exactly. "
            "It must support the claim its marker is attached to."
        )
    )


class Decision(BaseModel):
    """The model's proposal. The rails decide what happens to it."""

    outcome: Outcome
    rationale: str = Field(
        description="Why, in a few sentences, with [n] markers referencing the citations"
    )
    citations: list[PolicyCitation] = Field(default_factory=list)
    assignee_hint: str | None = Field(
        default=None,
        description="A cost centre or role that should approve. Never a named person.",
    )
    unmet_conditions: list[str] = Field(
        default_factory=list,
        description="Policy conditions this document does not satisfy, in plain language",
    )
