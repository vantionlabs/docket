"""Tenders: the second vertical, and the proof the pipeline is generic.

Nothing in the pipeline changed to add this. No new node, no branch in
`decide`, no edit to coverage, grounding or the rails. That was the claim in
spec section 3 and it was not true until the invoice vertical moved out of
the pipeline; this file is what tests it.

What differs from invoices is exactly what a Vertical is allowed to differ
in: the schema, the dimensions a policy can impose, how the retrieval query
is built, how the document is shown, and which checks run in code. Note that
almost none of the invoice dimensions survive. A tender has no VAT rate and
no purchase order; an invoice has no delivery window and no penalty clause.
That is the point of dimensions being per-vertical.
"""

import re
from datetime import date
from decimal import Decimal

from app.extraction.schemas.tender import SCHEMA_NAME, Tender
from app.verticals.base import DeterministicChecks, warnings_block

_WORD = re.compile(r"[a-z0-9]+")


class TenderVertical:
    name = SCHEMA_NAME
    schema = Tender

    dimensions = frozenset(
        {
            "value",  # the authority's estimate against our bid thresholds
            "deadline",  # submission and completion dates
            "penalty",  # liquidated damages for delay
            "security",  # borgtocht, guarantees, retention
            "certification",  # required qualifications and standards
            "insurance",
            "materials",  # specified products and standards
            "exclusion",  # what the tender does not cover
            "scope",  # what our own policy covers at all
            "escalation",  # what to do when policy does not settle it
        }
    )

    def check(self, document: Tender) -> DeterministicChecks:
        """Dates in order, and a deposit that does not exceed the work.

        Arithmetic is the invoice's version of this. A tender's equivalent
        is chronology and proportion, and the reasoning is identical: a
        model asked to compare two dates will sometimes compare them wrong,
        and there is no reason to ask.
        """
        failures: list[str] = []

        def value_of(field) -> date | Decimal | None:
            return field.value if field is not None else None

        deadline = value_of(document.submission_deadline)
        start = value_of(document.works_start)
        completion = value_of(document.works_completion)

        if start and deadline and start < deadline:
            failures.append(
                f"works start {start} is before the submission deadline {deadline}"
            )
        if start and completion and completion < start:
            failures.append(f"completion {completion} is before works start {start}")

        estimated = value_of(document.estimated_value)
        deposit = value_of(document.security_deposit)
        if estimated and deposit and deposit > estimated:
            failures.append(
                f"security deposit {deposit} exceeds the estimated value {estimated}"
            )

        return DeterministicChecks(ok=not failures, failures=failures)

    def query(self, document: Tender) -> str:
        """Named by dimension, not only by the tender's own words.

        The same lesson as the invoice query. A tender that says "borgtocht
        van 5%" and a policy that says "we do not tender where a security
        deposit above 5 percent is required" share no token, and the rule
        that would have stopped the bid is never retrieved.
        """
        parts = [
            f"project {document.project.value}",
            f"authority {document.contracting_authority.value}",
        ]
        if document.estimated_value is not None:
            parts.append(
                f"estimated value {document.estimated_value.value} {document.currency.value}"
            )
        if document.security_deposit is not None:
            parts.append("security deposit, borgtocht, guarantee required")
        if document.delay_penalty_per_day is not None:
            parts.append("liquidated damages, penalty for delay per day")
        parts.extend(
            r.description.value for r in document.priced_requirements[:8]
        )
        parts.append(
            "bid thresholds and approval authority, required certification, insurance "
            "cover, materials standards, submission deadline, completion date, "
            "exclusions we do not accept"
        )
        return ", ".join(parts)

    def render(
        self, document: Tender, checks: DeterministicChecks, unverified: list[str]
    ) -> str:
        lines = [
            "TENDER (extracted):",
            f"  reference: {document.reference.value}",
            f"  authority: {document.contracting_authority.value}",
            f"  project: {document.project.value}",
            f"  submission deadline: {document.submission_deadline.value}",
            f"  works: {_span(document.works_start)} to {_span(document.works_completion)}",
            f"  estimated value: {_span(document.estimated_value)} {document.currency.value}",
            f"  security deposit: {_span(document.security_deposit)}",
            f"  delay penalty per day: {_span(document.delay_penalty_per_day)}",
        ]
        priced = document.priced_requirements
        if priced:
            lines.append(f"  requirements that affect price ({len(priced)}):")
            lines.extend(
                f"    - [{r.category.value}] {r.description.value}" for r in priced
            )
        other = [r for r in document.requirements if not r.affects_price.value]
        if other:
            lines.append(f"  other requirements: {len(other)}")

        return "\n".join(lines + warnings_block(checks, unverified))

    def triggers(self, document: Tender, checks: DeterministicChecks) -> set[str]:
        triggered = {"value", "deadline", "certification", "materials", "exclusion"}
        if document.security_deposit is not None:
            triggered.add("security")
        if document.delay_penalty_per_day is not None:
            triggered.add("penalty")
        if any(r.category.value.lower() == "insurance" for r in document.requirements):
            triggered.add("insurance")
        if not checks.ok:
            triggered.add("deadline")
        return triggered

    def subject_terms(self, document: Tender) -> set[str]:
        """What the work is, for matching `applies_when`.

        The project description and the requirement categories. The
        contracting authority is excluded for the same reason a supplier
        name is on an invoice: it says who is buying, not what is being
        built.
        """
        terms = set(_WORD.findall(str(document.project.value).lower()))
        for requirement in document.requirements:
            terms.update(_WORD.findall(str(requirement.category.value).lower()))
        return terms

    def amount(self, document: Tender) -> Decimal | None:
        return document.estimated_value.value if document.estimated_value else None


def _span(field) -> str:
    return str(field.value) if field is not None else "not stated"
