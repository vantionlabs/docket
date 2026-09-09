"""Coverage-checked retrieval: proving which rules were considered.

The bug these exist for: top-k retrieval can fail to return a clause that
applies, and nothing downstream notices. The verbatim check, the judge and
the reviewer all inspect what came back; none of them can see what did not.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.decisions.coverage import (
    CoverageReport,
    Obligation,
    check_coverage,
    triggered_dimensions,
)
from app.decisions.policy import CoveredPolicy, PolicyClause, PolicyCorpus
from app.extraction.provenance import ExtractedField
from app.extraction.schemas.invoice import Invoice
from app.verticals import get_vertical
from app.verticals.base import DeterministicChecks

INVOICE = get_vertical("invoice")


def _f(value):
    return ExtractedField(value=value, source_span=str(value))


def _invoice(currency="EUR", issued="2026-02-12", due=None):
    return Invoice(
        supplier=_f("Contoso Cleaning Services BV"),
        invoice_number=_f("CCS-1"),
        total_incl_vat=_f(Decimal("859.10")),
        vat_amount=_f(Decimal("149.10")),
        currency=_f(currency),
        issued_on=_f(date.fromisoformat(issued)),
        due_on=_f(date.fromisoformat(due)) if due else None,
    )


def _obligation(dimension, clause_id=None, chunk_id=None, always=False, about=()):
    """`clause_id` is what a markdown corpus calls the clause; `chunk_id` is
    what the database calls it. An obligation carries whichever its policy
    source uses, and `clause_key` picks."""
    return Obligation(
        id=clause_id or f"obligation-for-{dimension}",
        dimension=dimension,
        summary=f"a rule about {dimension}",
        clause_ref=f"clause for {dimension}",
        chunk_id=chunk_id,
        always_applies=always,
        applies_when=tuple(about),
    )


# --- what puts a rule in play -------------------------------------------


def test_a_euro_invoice_does_not_trigger_the_currency_dimension():
    assert "currency" not in triggered_dimensions(_invoice(), INVOICE)


def test_a_usd_invoice_triggers_the_currency_dimension():
    """The M1 bug, now a trigger rather than a hope about the query."""
    assert "currency" in triggered_dimensions(_invoice(currency="USD"), INVOICE)


def test_currency_matching_is_case_and_space_insensitive():
    assert "currency" not in triggered_dimensions(_invoice(currency=" eur "), INVOICE)


def test_the_always_present_dimensions_are_always_triggered():
    """Amount and supplier apply to every invoice, which is exactly why
    they are the easiest ones to forget to ask about."""
    dimensions = triggered_dimensions(_invoice(), INVOICE)
    assert {"amount", "supplier", "purchase_order"} <= dimensions


def test_short_payment_terms_trigger_the_payment_dimension():
    assert "payment_terms" in triggered_dimensions(
        _invoice(issued="2026-02-12", due="2026-02-19"), INVOICE
    )


def test_bad_arithmetic_triggers_vat():
    checks = DeterministicChecks(ok=False, failures=["VAT does not add up"])
    assert "vat" in triggered_dimensions(_invoice(), INVOICE, checks)


# --- the check ----------------------------------------------------------


def test_a_retrieved_obligation_is_covered():
    chunk = uuid.uuid4()
    report = check_coverage(
        [_obligation("amount", chunk_id=chunk)],
        {"amount"},
        {str(chunk)},
    )
    assert report.complete
    assert report.recall == 1.0


def test_an_untriggered_obligation_is_not_required():
    """A rule that does not apply is not a gap when it is absent."""
    report = check_coverage([_obligation("currency")], {"amount"}, set())
    assert report.triggered == []
    assert report.complete


def test_a_triggered_obligation_that_was_not_retrieved_is_a_gap():
    report = check_coverage([_obligation("currency")], {"currency"}, set())
    assert not report.complete
    assert report.missed[0].dimension == "currency"
    assert "was not retrieved" in report.notes()[0]


def test_always_applies_obligations_are_required_regardless():
    report = check_coverage(
        [_obligation("escalation", always=True)], set(), set()
    )
    assert report.triggered
    assert not report.complete


def test_recall_is_measured_per_decision_not_per_query():
    """Four of five rules found is not eighty percent right, but it is what
    the eval reports, so it has to be computed the obvious way."""
    chunk = uuid.uuid4()
    report = check_coverage(
        [
            _obligation("amount", chunk_id=chunk),
            _obligation("currency"),
        ],
        {"amount", "currency"},
        {str(chunk)},
    )
    assert report.recall == 0.5


def test_no_applicable_rules_is_full_recall_not_a_divide_by_zero():
    assert CoverageReport().recall == 1.0


# --- repair -------------------------------------------------------------


class _RankingOnly:
    """A source whose ranking misses the currency clause, like the real one
    did."""

    def __init__(self, corpus: PolicyCorpus, hide: set[str]) -> None:
        self.corpus = corpus
        self.hide = hide
        self.lookups: list = []

    def retrieve(self, query: str, top_k: int = 8):
        return [c for c in self.corpus.retrieve(query, top_k) if c.id not in self.hide]

    def by_chunk_ids(self, chunk_ids: list):
        self.lookups.append(list(chunk_ids))
        return self.corpus.by_chunk_ids(chunk_ids)


@pytest.fixture
def corpus():
    return PolicyCorpus.from_markdown(
        "## 3. Spend thresholds\n\nUp to EUR 1,000: the cost centre owner may approve.\n\n"
        "## 8. Currency\n\nInvoices are payable in euro. An invoice presented in another "
        "currency must be routed to Finance.\n"
    )


def test_a_missed_clause_is_repaired_not_merely_reported(corpus):
    """The point of the whole module. A warning helps whoever reads logs;
    pulling the clause in helps the decision that is about to be made."""
    currency_clause = next(c for c in corpus.clauses if c.ref.startswith("8."))
    inner = _RankingOnly(corpus, hide={currency_clause.id})

    covered = CoveredPolicy(
        inner,
        obligations=[_obligation("currency", currency_clause.id)],
        triggered={"currency"},
    )
    clauses = covered.retrieve("supplier amount threshold")

    assert currency_clause.id in {c.id for c in clauses}, "the missed clause was not pulled in"
    assert covered.report.complete, "a repaired gap must not still count as missed"
    assert inner.lookups == [[currency_clause.id]]


def test_an_unrepairable_gap_survives_as_a_gap(corpus):
    """An obligation whose clause no longer exists cannot be fetched, and
    must not be quietly forgiven."""
    inner = _RankingOnly(corpus, hide=set())
    covered = CoveredPolicy(
        inner,
        obligations=[_obligation("currency", "clause-that-was-deleted")],
        triggered={"currency"},
    )
    covered.retrieve("anything")
    assert not covered.report.complete


def test_nothing_is_fetched_when_ranking_already_covered_it(corpus):
    inner = _RankingOnly(corpus, hide=set())
    covered = CoveredPolicy(
        inner,
        obligations=[
            _obligation("currency", next(
                c.id for c in corpus.clauses if c.ref.startswith("8.")
            ))
        ],
        triggered={"currency"},
    )
    covered.retrieve("currency euro")
    assert inner.lookups == [], "repair ran when there was nothing to repair"
    assert covered.report.complete


def test_repair_does_not_duplicate_a_clause(corpus):
    inner = _RankingOnly(corpus, hide=set())
    covered = CoveredPolicy(inner, obligations=[], triggered=set())
    clauses = covered.retrieve("threshold")
    assert len({c.id for c in clauses}) == len(clauses)


def test_clause_lookup_returns_only_what_was_asked_for(corpus):
    wanted = corpus.clauses[0].id
    assert [c.id for c in corpus.by_chunk_ids([wanted])] == [wanted]
    assert corpus.by_chunk_ids([]) == []


def test_isinstance_of_policy_clause(corpus):
    assert all(isinstance(c, PolicyClause) for c in corpus.retrieve("euro"))


# --- obligation scope (found by a multi-document corpus) ----------------


def test_load_obligations_filters_by_schema_and_force(monkeypatch):
    """A policy corpus is not one policy.

    Loading every obligation in the org meant a supplier invoice was checked
    against expense-claim thresholds from the travel policy and spend limits
    from a superseded 2024 version, and the repair step dutifully fetched
    those clauses into the evidence. A single-document corpus cannot show
    this; the first multi-document one showed it immediately.
    """
    from unittest.mock import MagicMock

    from app.decisions.coverage import load_obligations

    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    load_obligations(db, uuid.uuid4(), "invoice")

    where = str(db.scalars.call_args[0][0])
    assert "schema_name" in where, "obligations were not filtered by what they govern"
    assert "in_force" in where, "superseded obligations were not filtered out"


def test_an_unknown_dimension_is_skipped_not_assumed_covered():
    """A rule this build cannot evaluate must not be silently treated as
    satisfied. Skipping it is honest; counting it as covered is not."""
    from unittest.mock import MagicMock

    from app.decisions.coverage import load_obligations

    row = MagicMock(dimension="a_dimension_from_the_future", threshold=None)
    row.id = uuid.uuid4()
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]

    assert load_obligations(db, uuid.uuid4(), "invoice") == []


# --- applicability: what a rule is ABOUT, not just what kind it is ------


def test_a_category_rule_does_not_bear_on_another_category():
    """The bug: "Catering and hospitality commitments up to EUR 50,000 may be
    approved by a department head" is a real, in-force, invoice-governing
    `amount` rule with nothing to say about a cleaning invoice. Every invoice
    triggers `amount`, so all fifteen category ladders were required and
    eight of them were repaired into the evidence every time."""
    catering = _obligation("amount", about=("catering", "hospitality"))
    cleaning_invoice = {"office", "cleaning", "monthly", "consumables"}

    assert not catering.bears_on({"amount"}, cleaning_invoice)


def test_a_category_rule_bears_on_its_own_category():
    catering = _obligation("amount", about=("catering", "hospitality"))
    assert catering.bears_on({"amount"}, {"adventure", "works", "catering"})


def test_an_unconditional_rule_bears_on_everything():
    """Most rules are like this: a EUR 500 PO threshold is about any purchase."""
    general = _obligation("purchase_order")
    assert general.bears_on({"purchase_order"}, {"anything", "at", "all"})


def test_an_unknown_subject_keeps_every_conditional_rule():
    """Skipping a rule that did matter is the failure this module exists to
    prevent, so not knowing the subject errs toward requiring more."""
    catering = _obligation("amount", about=("catering",))
    assert catering.bears_on({"amount"}, None)


def test_the_dimension_gate_still_applies_first():
    """A currency rule about catering is still not required by an invoice
    that does not put currency in play."""
    rule = _obligation("currency", about=("catering",))
    assert not rule.bears_on({"amount"}, {"catering"})


def test_coverage_skips_rules_that_do_not_bear_on_the_document():
    report = check_coverage(
        [
            _obligation("amount", "general"),
            _obligation("amount", "telecoms", about=("telecoms",)),
        ],
        {"amount"},
        set(),
        terms={"contoso", "cleaning"},
    )
    assert [o.id for o in report.triggered] == ["general"]


def test_subject_terms_reads_supplier_cost_centre_and_lines():
    from decimal import Decimal

    from app.decisions.coverage import subject_terms
    from app.extraction.schemas.invoice import LineItem

    invoice = _invoice()
    invoice.cost_centre = _f("FAC-01")
    invoice.line_items = [
        LineItem(
            description=_f("Catering, per head"),
            quantity=_f(Decimal(10)),
            unit_price=_f(Decimal("28.50")),
            amount=_f(Decimal("285.00")),
        )
    ]
    terms = subject_terms(invoice, INVOICE)
    assert {"catering", "head", "fac", "01"} <= terms


def test_subject_terms_survives_a_sparse_invoice():
    """An extraction that read almost nothing must not blow up the check."""
    from app.decisions.coverage import subject_terms

    assert subject_terms(object(), INVOICE) == set()


def test_the_supplier_name_is_not_a_subject_term():
    """"Contoso Cleaning Services BV" contributed the token `services`,
    which matched the delegation matrix's "Legal Services" ladder and pulled
    it into the evidence for a cleaning invoice. A trading name says who
    sold, not what was bought."""
    from decimal import Decimal

    from app.decisions.coverage import subject_terms
    from app.extraction.schemas.invoice import LineItem

    invoice = _invoice()  # supplier: Contoso Cleaning Services BV
    invoice.line_items = [
        LineItem(
            description=_f("Office cleaning, monthly"),
            quantity=_f(Decimal(1)),
            unit_price=_f(Decimal("620.00")),
            amount=_f(Decimal("620.00")),
        )
    ]
    terms = subject_terms(invoice, INVOICE)
    assert "services" not in terms
    assert "contoso" not in terms
    assert {"office", "cleaning", "monthly"} <= terms

    legal = _obligation("amount", about=("legal", "services"))
    assert not legal.bears_on({"amount"}, terms)
