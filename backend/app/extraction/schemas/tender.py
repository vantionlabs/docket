"""Tender requirements: the bestek, read as typed rows with provenance.

A Belgian construction tender arrives as a pair. The *bestek* is the written
specification, a hundred-odd pages of conditions: materials and their
standards, execution method, timelines, penalties for delay, insurance,
exclusions. The *meetstaat* is the bill of quantities being priced.

The estimator prices the meetstaat. The bestek is what makes those prices
right or wrong, and missing one clause on page sixty-three means
underpricing the job and eating the difference. That is the same failure the
invoice vertical was built for, with the money moving in the other
direction: a missed clause looks exactly like a satisfied one.

The schema is the requirements pulled *out* of the tender, each carrying the
verbatim span it was read from, so a quote can be checked against them.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.extraction.provenance import ExtractedField

SCHEMA_NAME = "tender"


class Requirement(BaseModel):
    """One condition the tender imposes that could change a price."""

    description: ExtractedField[str] = Field(
        description="What is required, in the tender's own terms"
    )
    category: ExtractedField[str] = Field(
        description=(
            "What kind of requirement: materials, execution, timeline, "
            "penalty, insurance, certification, exclusion, payment"
        )
    )
    affects_price: ExtractedField[bool] = Field(
        description="True when meeting this condition costs money or time"
    )


class Tender(BaseModel):
    """A tender, as the fields that decide whether to bid and at what price."""

    reference: ExtractedField[str] = Field(description="The tender's own reference number")
    contracting_authority: ExtractedField[str] = Field(
        description="Who is putting the work out to tender"
    )
    project: ExtractedField[str] = Field(description="What is being built")
    submission_deadline: ExtractedField[date]
    works_start: ExtractedField[date] | None = None
    works_completion: ExtractedField[date] | None = None
    estimated_value: ExtractedField[Decimal] | None = Field(
        default=None, description="The authority's own estimate, where stated"
    )
    currency: ExtractedField[str] = Field(description="ISO 4217 code, e.g. EUR")
    security_deposit: ExtractedField[Decimal] | None = Field(
        default=None, description="Borgtocht, where one is required"
    )
    delay_penalty_per_day: ExtractedField[Decimal] | None = None
    requirements: list[Requirement] = Field(default_factory=list)

    @property
    def priced_requirements(self) -> list[Requirement]:
        """The conditions that cost money. The ones a quote must answer."""
        return [r for r in self.requirements if r.affects_price.value]
