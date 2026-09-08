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
    """The model's proposal. The rails decide what happens to it.

    **Field order matters here.** Structured output is generated in
    declaration order, so `citations` is declared before `rationale`: the
    model chooses and numbers its clauses first, then writes prose that
    refers to numbers it has already committed to.

    The other way round, which this used to be, asks it to write `[7]` in
    the middle of a paragraph and only afterwards work out what citation 7
    is. Across a long rationale it loses track, and a marker with no entry
    behind it is an unverifiable claim that fails grounding. That single
    ordering accounted for 25 of 66 grounding failures on a 99-case run.
    """

    outcome: Outcome
    citations: list[PolicyCitation] = Field(
        default_factory=list,
        description=(
            "The clauses that decide this case, numbered from 1. Choose these "
            "BEFORE writing the rationale, and keep the list short."
        ),
    )
    rationale: str = Field(
        description=(
            "Why, in a few sentences, using [n] markers that refer to the "
            "citations above. Never write a marker with no citation behind it."
        )
    )
    assignee_hint: str | None = Field(
        default=None,
        description="A cost centre or role that should approve. Never a named person.",
    )
    unmet_conditions: list[str] = Field(
        default_factory=list,
        description="Policy conditions this document does not satisfy, in plain language",
    )
