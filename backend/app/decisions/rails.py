"""The three hard rails (spec section 9). These are the spec, not a default.

1. A decision that fails grounding never executes. It becomes needs_human
   with the failure attached.
2. Any unverified extracted field forces review, whatever the outcome says.
3. Auto-approve is gated by an explicit rule, not by model confidence.
   The model proposes; the rule decides whether a human sees it. A model's
   own confidence score is not an authorisation.

The rails only ever move a decision toward a human. Nothing in here can
turn a route_for_approval into an auto_approve, which is why this is the
last thing that touches an outcome.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from app.decisions.decide import DecisionResult
from app.decisions.models import Outcome
from app.extraction.schemas.invoice import Invoice

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.db.models import Rule as RuleRow


@dataclass
class AutoApproveRule:
    """The explicit gate of rail 3. Every condition must hold.

    In the built pipeline this is a `rules` row per org (spec section 12).
    In the spike it is a dataclass, and `active=False` is the default
    because v1 ships with everything queued (spec section 4).
    """

    name: str
    max_total_incl_vat: Decimal
    approved_suppliers: frozenset[str] = frozenset()
    require_po: bool = True
    active: bool = False

    def unmet(self, invoice: Invoice) -> list[str]:
        """Which of this rule's conditions the invoice fails."""
        failures: list[str] = []
        if invoice.total_incl_vat.value > self.max_total_incl_vat:
            failures.append(
                f"total {invoice.total_incl_vat.value} is over the "
                f"{self.name} limit of {self.max_total_incl_vat}"
            )
        if self.approved_suppliers and not _is_approved(
            invoice.supplier.value, self.approved_suppliers
        ):
            failures.append(f"supplier {invoice.supplier.value!r} is not on the approved list")
        if self.require_po and invoice.po_number is None:
            failures.append("no purchase order number on the invoice")
        return failures


def _is_approved(supplier: str, approved: frozenset[str]) -> bool:
    normalized = " ".join(supplier.split()).casefold()
    return any(normalized == " ".join(name.split()).casefold() for name in approved)


@dataclass
class FinalDecision:
    """What actually happens, after the rails have had their say."""

    outcome: Outcome
    rationale: str
    unmet_conditions: list[str]
    assignee_hint: str | None
    grounding_passed: bool
    rule_id: str | None = None
    """The rule that authorised an auto-approve. None means no rule did."""
    rail_notes: list[str] = field(default_factory=list)
    """Why the rails changed the outcome, if they did. Shown to the reviewer."""
    citations: list[tuple[int, str, str]] = field(default_factory=list)
    """(index, clause ref, excerpt) for the audit trail."""

    @property
    def executes_automatically(self) -> bool:
        return self.outcome is Outcome.auto_approve


_CITED_UNRETRIEVED = "which was not offered this turn"


def _grounding_note(failure: str) -> str:
    """Say what went wrong in words a reviewer can act on.

    The failure strings are precise and are written for whoever debugs the
    pipeline. A person clearing a queue needs to know one thing: the reason
    given for this decision does not hold up, so read it yourself.
    """
    if "no citations" in failure:
        return (
            "The pipeline reached this outcome without pointing at any policy "
            "clause, so there is nothing to check it against. Decide this one "
            "yourself."
        )
    if "not verbatim" in failure:
        return (
            "A policy clause was quoted inexactly, so the quote could not be "
            "confirmed against the policy. Read the clause before deciding."
        )
    if _CITED_UNRETRIEVED in failure:
        return (
            "A policy clause was cited that was never retrieved, so it cannot "
            "be shown to you. Decide this one yourself."
        )
    if "judge rejected" in failure:
        return (
            "A policy clause was quoted correctly but does not support the "
            "claim it was attached to, so the reasoning does not hold up. "
            "Read the clauses yourself."
        )
    if "no policy clauses retrieved" in failure:
        return (
            "No policy clause was found for this document. Either the policy "
            "does not cover it, or the corpus is missing something."
        )
    return f"The decision could not be grounded in policy: {failure}"


def apply_rails(
    result: DecisionResult,
    invoice: Invoice,
    unverified_fields: list[str],
    arithmetic_failures: list[str],
    rule: AutoApproveRule | None = None,
) -> FinalDecision:
    proposed = result.decision
    notes: list[str] = []
    unmet = list(proposed.unmet_conditions)
    outcome = proposed.outcome
    rule_id: str | None = None

    # Rail 1: grounding.
    if not result.grounding_passed:
        outcome = Outcome.needs_human
        notes.append(_grounding_note(result.grounding_failure))

    # Rail 1b: coverage. A decision reached without a rule that applies was
    # not made on the policy, whatever it cited. Only gaps that could not be
    # repaired reach here; anything retrieval could fetch was already added
    # to the evidence before the model saw it.
    coverage = getattr(result, "coverage", None)
    if coverage is not None and not coverage.complete:
        outcome = Outcome.needs_human
        notes.extend(coverage.notes())
        unmet.extend(
            f"policy rule not considered: {o.clause_ref}" for o in coverage.missed
        )

    # Rail 2: unverified fields.
    if unverified_fields:
        if outcome is Outcome.auto_approve:
            outcome = Outcome.route_for_approval
        notes.append(
            "These fields could not be verified against the document: "
            + ", ".join(unverified_fields)
        )
        unmet.extend(f"unverified field: {name}" for name in unverified_fields)

    # Arithmetic is not its own rail, but it is never an automatic approval.
    if arithmetic_failures:
        if outcome is Outcome.auto_approve:
            outcome = Outcome.route_for_approval
        notes.append("The arithmetic does not check out: " + "; ".join(arithmetic_failures))
        unmet.extend(arithmetic_failures)

    # Rail 3: auto-approve needs an explicit, active rule that passes.
    if outcome is Outcome.auto_approve:
        if rule is None or not rule.active:
            outcome = Outcome.route_for_approval
            notes.append(
                "No active auto-approve rule covers this document, so it goes to a reviewer."
            )
        else:
            rule_failures = rule.unmet(invoice)
            if rule_failures:
                outcome = Outcome.route_for_approval
                notes.append(
                    f"Rule {rule.name!r} does not permit auto-approval: " + "; ".join(rule_failures)
                )
                unmet.extend(rule_failures)
            else:
                rule_id = rule.name

    return FinalDecision(
        outcome=outcome,
        rationale=proposed.rationale,
        unmet_conditions=unmet,
        assignee_hint=proposed.assignee_hint,
        grounding_passed=result.grounding_passed,
        rule_id=rule_id,
        rail_notes=notes,
        citations=[(index, clause.ref, excerpt) for index, clause, excerpt in result.cited],
    )


def from_row(row: "RuleRow") -> AutoApproveRule:
    """Build the rail-3 gate from a `rules` row.

    Unknown or missing conditions are not permissive. A rule with no
    `max_total_incl_vat` gets a limit of zero rather than infinity, so a
    half-configured rule approves nothing instead of everything.
    """
    conditions = row.conditions or {}
    return AutoApproveRule(
        name=row.name,
        max_total_incl_vat=Decimal(str(conditions.get("max_total_incl_vat", "0"))),
        approved_suppliers=frozenset(conditions.get("approved_suppliers") or ()),
        require_po=bool(conditions.get("require_po", True)),
        active=bool(row.active and row.auto_approve),
    )


def rule_for(db: "Session", org_id: "uuid.UUID | None", schema_name: str) -> AutoApproveRule | None:
    """The active auto-approve rule for this org and schema, if any.

    Returns None when nothing is configured, which is the v1 default and
    means everything queues (spec section 4). Where several rules match,
    the newest wins; a client with two overlapping rules has a
    configuration problem, and silently picking the most permissive one
    would hide it.
    """
    from sqlalchemy import select

    from app.db.models import Rule as RuleRow

    row = db.scalar(
        select(RuleRow)
        .where(
            RuleRow.org_id == org_id,
            RuleRow.schema_name == schema_name,
            RuleRow.active.is_(True),
            RuleRow.auto_approve.is_(True),
        )
        .order_by(RuleRow.created_at.desc())
        .limit(1)
    )
    return from_row(row) if row is not None else None
