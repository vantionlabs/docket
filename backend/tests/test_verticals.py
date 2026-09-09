"""The claim of spec section 3, tested rather than asserted.

"The pipeline is the product; the vertical is configuration — build it so
swapping those three is a day, not a fork." That was aspiration until M8:
`decide.py` carried thirty-three references to invoices, `coverage.py`
fifteen, `rails.py` ten.

These tests do not check that tenders are decided *well* — that is what the
eval is for, and it needs a tender corpus and a model. They check the
structural claim underneath: a second document type runs through the same
retrieval, the same coverage check, the same grounding and the same rails,
with no branch anywhere in the pipeline that names it.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.decisions.coverage import Obligation, check_coverage, subject_terms, triggered_dimensions
from app.decisions.decide import check_citations
from app.decisions.models import Decision, Outcome, PolicyCitation
from app.decisions.policy import CoveredPolicy, PolicyClause, PolicyCorpus
from app.decisions.rails import apply_rails
from app.extraction.provenance import ExtractedField
from app.extraction.schemas.tender import Requirement, Tender
from app.verticals import get_vertical, registered_verticals
from app.verticals.base import DeterministicChecks, all_dimensions

INVOICE = get_vertical("invoice")
TENDER = get_vertical("tender")


def _f(value):
    return ExtractedField(value=value, source_span=str(value))


def _tender(deadline="2026-11-30", start="2027-01-15", completion="2027-09-30",
            value="1850000.00", deposit="92500.00"):
    return Tender(
        reference=_f("2026/AD/0417"),
        contracting_authority=_f("Stad Antwerpen"),
        project=_f("Renovatie schoolgebouw Deurne, dakwerken en gevelisolatie"),
        submission_deadline=_f(date.fromisoformat(deadline)),
        works_start=_f(date.fromisoformat(start)),
        works_completion=_f(date.fromisoformat(completion)),
        estimated_value=_f(Decimal(value)),
        currency=_f("EUR"),
        security_deposit=_f(Decimal(deposit)) if deposit else None,
        delay_penalty_per_day=_f(Decimal("1250.00")),
        requirements=[
            Requirement(
                description=_f("Dakisolatie minimaal R = 6,0 m²K/W"),
                category=_f("materials"),
                affects_price=_f(True),
            ),
            Requirement(
                description=_f("Aansprakelijkheidsverzekering minimaal EUR 2.500.000"),
                category=_f("insurance"),
                affects_price=_f(True),
            ),
        ],
    )


# --- the registry --------------------------------------------------------


def test_both_verticals_are_registered():
    assert registered_verticals() == ["invoice", "tender"]


def test_an_unknown_vertical_raises_rather_than_defaulting():
    """Falling back to invoices would decide a tender against procurement
    thresholds and produce something that looks like it worked."""
    with pytest.raises(KeyError, match="No vertical registered"):
        get_vertical("purchase_order")


def test_the_two_verticals_barely_share_dimensions():
    """The reason dimensions moved out of a global enum. A tender has no VAT
    rate and no purchase order; an invoice has no delivery window."""
    shared = INVOICE.dimensions & TENDER.dimensions
    assert shared == {"scope", "escalation"}
    assert all_dimensions() == INVOICE.dimensions | TENDER.dimensions


def test_no_vertical_declares_a_dimension_it_cannot_trigger():
    """A dimension nothing ever triggers is a rule that is indexed, required
    by nothing, and so never checked — the failure this module exists for."""
    for vertical in (INVOICE, TENDER):
        assert vertical.dimensions >= vertical.triggers(
            _tender() if vertical is TENDER else _invoice(), DeterministicChecks()
        )


def _invoice():
    from app.extraction.schemas.invoice import Invoice, LineItem

    return Invoice(
        supplier=_f("Contoso Cleaning Services BV"),
        invoice_number=_f("INV-2026-0042"),
        total_incl_vat=_f(Decimal("859.10")),
        vat_amount=_f(Decimal("149.10")),
        currency=_f("EUR"),
        issued_on=_f(date(2026, 2, 12)),
        due_on=_f(date(2026, 3, 14)),
        po_number=_f("PO-2026-0088"),
        line_items=[
            LineItem(
                description=_f("Office cleaning, February"),
                quantity=_f(Decimal("1")),
                unit_price=_f(Decimal("710.00")),
                amount=_f(Decimal("710.00")),
            )
        ],
    )


# --- the checks that need no model ---------------------------------------


def test_a_tender_with_dates_out_of_order_fails_its_checks():
    """The tender's answer to invoice arithmetic. Same argument: a model
    asked to compare two dates will sometimes compare them wrong."""
    checks = TENDER.check(_tender(start="2027-09-30", completion="2027-01-15"))
    assert not checks.ok
    assert any("completion" in f.lower() for f in checks.failures)


def test_a_clean_tender_passes_its_checks():
    assert TENDER.check(_tender()).ok


# --- the pipeline itself, with a tender through it ------------------------


def test_coverage_runs_over_tender_dimensions_unchanged():
    """`check_coverage` never learns what kind of document it is looking at.
    It compares triggered dimensions to indexed obligations, and that is the
    same operation for a bestek as for an invoice."""
    tender = _tender()
    triggered = triggered_dimensions(tender, TENDER, TENDER.check(tender))
    assert {"value", "deadline", "security", "penalty"} <= triggered

    obligations = [
        Obligation(id="ob-1", dimension="value", summary="Bids above EUR 1M need board sign-off",
                   clause_ref="4. Bid authority", chunk_id="chunk-1"),
        Obligation(id="ob-2", dimension="security", summary="Borgtocht is capped at 5%",
                   clause_ref="7. Security", chunk_id="chunk-2"),
    ]
    report = check_coverage(obligations, triggered, {"chunk-1"})
    assert not report.complete
    assert [o.clause_ref for o in report.missed] == ["7. Security"]


def test_the_repair_step_fetches_a_missed_tender_clause():
    """The whole point of coverage-checked retrieval, on the second vertical:
    a rule that applies and was not retrieved gets pulled in before the model
    decides, not merely logged after it."""
    clauses = [
        PolicyClause(id="c1", ref="4. Bid authority",
                     text="Bids above EUR 1,000,000 require board sign-off."),
        PolicyClause(id="c2", ref="7. Security",
                     text="A borgtocht above five per cent of the contract value is refused."),
    ]

    class _RanksOnly(PolicyCorpus):
        def __init__(self):
            self.clauses = clauses

        def retrieve(self, query, top_k=8):
            return [clauses[0]]  # never returns the security clause

        def by_ids(self, ids):
            return [c for c in clauses if c.id in set(ids)]

    covered = CoveredPolicy(
        _RanksOnly(),
        obligations=[Obligation(id="ob", dimension="security", summary="borgtocht cap",
                                clause_ref="7. Security", chunk_id="c2")],
        triggered={"security"},
        terms=subject_terms(_tender(), TENDER),
    )
    retrieved = covered.retrieve(TENDER.query(_tender()))
    assert {c.id for c in retrieved} == {"c1", "c2"}


def test_the_citation_check_is_the_same_check_for_a_tender():
    """`check_citations` reads the decision and the clauses, never the
    document. A verbatim quote of a bestek clause passes exactly as an
    invoice's does; an invented one fails exactly as an invoice's does."""
    clause = PolicyClause(
        id="c2",
        ref="7. Security",
        text="A borgtocht above five per cent of the contract value is refused.",
    )
    excerpt = "A borgtocht above five per cent of the contract value is refused."
    decision = Decision(
        outcome=Outcome.route_for_approval,
        rationale="The deposit is five per cent of the estimate [1].",
        citations=[PolicyCitation(index=1, clause_id="clause-1", excerpt=excerpt)],
    )
    result = check_citations(decision, [clause], labels={"clause-1": clause})
    assert result.grounding_passed

    invented = Decision(
        outcome=Outcome.auto_approve,
        rationale="Deposits under ten per cent are always fine [1].",
        citations=[
            PolicyCitation(index=1, clause_id="clause-1",
                           excerpt="Deposits under ten per cent are always fine.")
        ],
    )
    assert not check_citations(invented, [clause], labels={"clause-1": clause}).grounding_passed


def test_a_tender_queues_because_no_rule_authorises_it():
    """Rail 3 on the second vertical. No auto-approve rule is configured for
    tenders, so the rail routes to a human — which is the v1 default and the
    right answer, not a gap."""
    clause = PolicyClause(id="c1", ref="4. Bid authority", text="Bids need sign-off.")
    result = check_citations(
        Decision(outcome=Outcome.auto_approve, rationale="Fine [1].",
                 citations=[PolicyCitation(index=1, clause_id="clause-1",
                                           excerpt="Bids need sign-off.")]),
        [clause],
        labels={"clause-1": clause},
    )
    final = apply_rails(result, _tender(), [], [], rule=None)
    assert final.outcome is Outcome.route_for_approval
    assert not final.executes_automatically


def test_failed_tender_checks_block_auto_approval_like_failed_arithmetic():
    """The rails read `check_failures`, not arithmetic. Chronology failures
    on a tender are treated the way VAT failures on an invoice are."""
    clause = PolicyClause(id="c1", ref="4. Bid authority", text="Bids need sign-off.")
    result = check_citations(
        Decision(outcome=Outcome.auto_approve, rationale="Fine [1].",
                 citations=[PolicyCitation(index=1, clause_id="clause-1",
                                           excerpt="Bids need sign-off.")]),
        [clause],
        labels={"clause-1": clause},
    )
    tender = _tender(start="2027-09-30", completion="2027-01-15")
    final = apply_rails(result, tender, [], TENDER.check(tender).failures)
    assert final.outcome is Outcome.route_for_approval
    assert any("checks did not pass" in note for note in final.rail_notes)


# --- the query and the render --------------------------------------------


def test_the_tender_query_asks_the_policy_its_own_question():
    """The M1 lesson, applied to the second vertical: the query names the
    dimensions the policy speaks about, not only the values on the document.
    A query built from the tender's own words never retrieves a clause that
    talks about 'borgtocht' when the tender says 'security deposit'."""
    query = TENDER.query(_tender())
    for term in ("certification", "insurance", "deadline"):
        assert term in query


def test_the_render_carries_the_warnings_every_vertical_shows():
    tender = _tender(start="2027-09-30", completion="2027-01-15")
    rendered = TENDER.render(tender, TENDER.check(tender), ["estimated_value"])
    assert "could not be verified" in rendered
    assert "deterministic checks did not pass" in rendered
    assert "2026/AD/0417" in rendered
