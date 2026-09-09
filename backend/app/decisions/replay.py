"""What would have happened under a rule that does not exist yet.

A client asking whether to widen an auto-approve threshold is asking an
empirical question — *how many of last quarter's invoices would this have
let through, and were any of them ones we would have wanted to see?* — and
normally gets an answer built out of intuition, because the system that made
those decisions cannot be asked about decisions it did not make.

Docket can be asked, for one structural reason: the rails are deterministic.
Rail 3 reads an extracted document and a rule and returns a verdict with no
model involved, so given the extraction (stored, with spans), the model's
proposal (stored since 0011) and the grounding and coverage verdicts (also
stored), the whole of `apply_rails` can be re-run against a hypothetical
rule over five thousand past decisions in a second, for nothing.

Two rules govern this module, and both are about not overclaiming:

**It calls `apply_rails`, it does not reimplement it.** A replay that
computed outcomes its own way would be a second implementation of the rails,
free to drift from the first, and the moment it drifted every answer here
would be quietly wrong while still looking authoritative. The test that
matters is `test_replaying_the_current_rule_reproduces_history`: replay the
rule that actually ran and every decision must land where it landed.

**A rule change is exact; a policy change is not.** Editing rail 3's limit
changes only deterministic code. Editing a policy *clause* changes what the
model would have proposed, and nothing here can know that without asking it
again. So clause questions get `exposure()`, which answers the narrower
question exactly — which past decisions cited this clause, and what they
were worth — and refuses to guess at the rest.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.decisions.decide import DecisionResult
from app.decisions.models import Decision, Outcome
from app.decisions.rails import AutoApproveRule, apply_rails, from_row
from app.logging import get_logger
from app.verticals import get_vertical

log = get_logger(__name__)


@dataclass(frozen=True)
class _StoredCoverage:
    """Rail 1b's input, as it was recorded rather than recomputed.

    `apply_rails` asks a coverage report two things: whether it is complete,
    and what to tell a reviewer when it is not. Re-deriving the second would
    mean re-running retrieval, so the note says plainly that the gap is
    historical. The verdict — the part that moves an outcome — is the stored
    one, which is the part that has to be right.
    """

    complete: bool

    def notes(self) -> list[str]:
        if self.complete:
            return []
        return ["A policy rule that applies here was not retrieved (recorded at decision time)."]

    @property
    def missed(self) -> list:
        return []


@dataclass
class Flip:
    """One decision that lands somewhere else under the proposed rule."""

    decision_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    was: str
    would_be: str
    amount: Decimal | None
    supplier: str | None
    reason: str
    """The rail note that explains the new outcome, or "" when nothing had
    to be said because the rule simply permitted it."""

    @property
    def loosens(self) -> bool:
        """True when the change lets something through that a human saw."""
        return self.would_be == str(Outcome.auto_approve)


@dataclass
class ReplayReport:
    """The answer, with its own limits attached.

    `unreplayable` is not a rounding error to be hidden. A decision whose
    proposal was never recorded cannot be replayed, and reporting a flip
    count over a silently smaller population is exactly the class of mistake
    this project keeps finding in its own numbers.
    """

    considered: int = 0
    unreplayable: int = 0
    auto_approved_before: int = 0
    auto_approved_after: int = 0
    flips: list[Flip] = field(default_factory=list)

    @property
    def newly_automatic(self) -> list[Flip]:
        """Decisions a human saw that the proposed rule would not show them."""
        return [f for f in self.flips if f.loosens]

    @property
    def newly_reviewed(self) -> list[Flip]:
        """Decisions that were automatic and would now reach a human."""
        return [f for f in self.flips if not f.loosens]

    @property
    def value_newly_automatic(self) -> Decimal:
        """What the loosening is worth, and what it puts at risk. The same
        number reads as a saving or an exposure depending on which way the
        reader is arguing, which is why it is reported rather than framed."""
        return sum((f.amount or Decimal(0) for f in self.newly_automatic), Decimal(0))

    @property
    def automation_rate_before(self) -> float:
        return self.auto_approved_before / self.considered if self.considered else 0.0

    @property
    def automation_rate_after(self) -> float:
        return self.auto_approved_after / self.considered if self.considered else 0.0


def replay(
    db,
    org_id: uuid.UUID,
    rule: AutoApproveRule | None,
    schema_name: str = "invoice",
    limit: int | None = None,
) -> ReplayReport:
    """Re-run the rails over decided history under `rule`.

    `rule=None` is a real question, not a missing argument: it asks what the
    history looks like with rail 3 switched off entirely, which is the v1
    default and the baseline every proposed rule is measured against.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from app.db.models import Decision as DecisionRow
    from app.db.models import Extraction, SourceDocument

    vertical = get_vertical(schema_name)
    report = ReplayReport()

    query = (
        select(DecisionRow, Extraction, SourceDocument)
        .join(Extraction, DecisionRow.extraction_id == Extraction.id)
        .join(SourceDocument, DecisionRow.document_id == SourceDocument.id)
        .where(DecisionRow.org_id == org_id, Extraction.schema_name == schema_name)
        .order_by(DecisionRow.decided_at.desc())
        .options(joinedload(DecisionRow.citations))
    )
    if limit is not None:
        query = query.limit(limit)

    for row, extraction, document in db.execute(query).unique().all():
        if row.proposed_outcome is None:
            report.unreplayable += 1
            continue

        try:
            proposed = Outcome(row.proposed_outcome)
            extracted = vertical.schema.model_validate(extraction.fields)
        except Exception:  # noqa: BLE001 -- a row we cannot read is one we do not count
            log.warning("replay.unreadable_decision", decision_id=str(row.id))
            report.unreplayable += 1
            continue

        result = DecisionResult(
            decision=Decision(
                outcome=proposed,
                rationale=row.rationale,
                unmet_conditions=[],
                assignee_hint=row.assigned_to,
            ),
            clauses=[],
            grounding_passed=row.grounding_passed,
            grounding_failure=row.grounding_failure or "",
            coverage=(
                None if row.coverage_complete is None else _StoredCoverage(row.coverage_complete)
            ),
        )

        final = apply_rails(
            result,
            extracted,
            list(extraction.unverified_fields or []),
            list(extraction.arithmetic_failures or []),
            rule=rule,
        )

        report.considered += 1
        if row.outcome == str(Outcome.auto_approve):
            report.auto_approved_before += 1
        if final.outcome is Outcome.auto_approve:
            report.auto_approved_after += 1

        if str(final.outcome) != row.outcome:
            report.flips.append(
                Flip(
                    decision_id=row.id,
                    document_id=row.document_id,
                    filename=document.filename,
                    was=row.outcome,
                    would_be=str(final.outcome),
                    amount=vertical.amount(extracted),
                    supplier=_supplier(extracted),
                    reason=final.rail_notes[-1] if final.rail_notes else "",
                )
            )

    return report


def rule_from_conditions(
    name: str, conditions: dict, active: bool = True
) -> AutoApproveRule:
    """Build a hypothetical rail-3 gate from the same dict shape a `rules`
    row stores, so a replayed rule and a saved one are the same object.

    Goes through `from_row` deliberately: half-configured rules are
    permissive-looking and `from_row` is where that is already handled — a
    missing limit becomes zero rather than infinity. A replay that built the
    rule its own way would answer a question about a rule the system would
    never actually run.
    """

    class _Row:
        pass

    row = _Row()
    row.name = name
    row.conditions = conditions
    row.active = active
    row.auto_approve = True
    return from_row(row)


@dataclass
class Exposure:
    """Which decisions rest on one clause, and what they are worth."""

    clause_ref: str
    decisions: int = 0
    amount: Decimal = Decimal(0)
    outcomes: dict[str, int] = field(default_factory=dict)
    sample: list[tuple[uuid.UUID, str]] = field(default_factory=list)


def exposure(db, org_id: uuid.UUID, chunk_id: uuid.UUID, sample: int = 20) -> Exposure:
    """Every past decision that cited a given clause.

    The honest half of a policy-change question. Editing a clause changes
    what the model would propose, and nothing here can know that without
    asking it again — so this does not pretend to. It answers the part that
    is a fact: these decisions were reached by citing this text, so these
    are the ones a change to it puts in question. That set is what a policy
    owner actually needs before editing, and it is exact.
    """
    from sqlalchemy import select

    from app.db.models import Decision as DecisionRow
    from app.db.models import DecisionCitation, Extraction

    rows = db.execute(
        select(DecisionRow, DecisionCitation.clause_ref, Extraction)
        .join(DecisionCitation, DecisionCitation.decision_id == DecisionRow.id)
        .outerjoin(Extraction, DecisionRow.extraction_id == Extraction.id)
        .where(DecisionRow.org_id == org_id, DecisionCitation.chunk_id == chunk_id)
        .order_by(DecisionRow.decided_at.desc())
    ).all()

    found = Exposure(clause_ref=rows[0][1] if rows else "")
    seen: set[uuid.UUID] = set()
    for decision, clause_ref, extraction in rows:
        if decision.id in seen:
            continue  # a decision may cite the same clause twice
        seen.add(decision.id)
        found.clause_ref = clause_ref
        found.decisions += 1
        found.outcomes[decision.outcome] = found.outcomes.get(decision.outcome, 0) + 1
        if extraction is not None:
            total = (extraction.fields or {}).get("total_incl_vat") or {}
            if isinstance(total, dict) and total.get("value") is not None:
                found.amount += Decimal(str(total["value"]))
        if len(found.sample) < sample:
            found.sample.append((decision.id, decision.outcome))

    return found


def _supplier(document) -> str | None:
    for attribute in ("supplier", "contracting_authority"):
        field_value = getattr(document, attribute, None)
        if field_value is not None:
            return str(field_value.value)
    return None
