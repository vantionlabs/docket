"""The three hard rails, and the citation check they sit on top of.

These are the spec, not an opening position (section 9), so they get tests
that fail loudly rather than a comment saying they matter.
"""

from decimal import Decimal

import pytest

from app.decisions.decide import check_citations
from app.decisions.models import Decision, Outcome, PolicyCitation
from app.decisions.policy import PolicyClause, PolicyCorpus
from app.decisions.rails import AutoApproveRule, apply_rails
from app.extraction.provenance import ExtractedField
from app.extraction.schemas.invoice import Invoice

CLAUSE = PolicyClause(
    id="clause-3",
    ref="3. Spend thresholds and approval authority",
    text="## 3. Spend thresholds and approval authority\n\nUp to EUR 1,000: the cost "
    "centre owner may approve.",
)


def _field(value):
    return ExtractedField(value=value, source_span=str(value))


def _invoice(total="859.10", supplier="Contoso Cleaning Services BV", po="PO-2026-0088"):
    return Invoice(
        supplier=_field(supplier),
        invoice_number=_field("CCS-2026-0411"),
        total_incl_vat=_field(Decimal(total)),
        vat_amount=_field(Decimal("149.10")),
        currency=_field("EUR"),
        issued_on=_field("2026-02-12"),
        po_number=_field(po) if po else None,
    )


def _decision(outcome=Outcome.auto_approve, rationale="Under the limit [1].", citations=None):
    if citations is None:
        citations = [
            PolicyCitation(
                index=1,
                clause_id="clause-3",
                excerpt="Up to EUR 1,000: the cost centre owner may approve.",
            )
        ]
    return Decision(outcome=outcome, rationale=rationale, citations=citations)


def _rule(**overrides):
    defaults = {
        "name": "cost-centre-owner-limit",
        "max_total_incl_vat": Decimal("1000"),
        "approved_suppliers": frozenset({"Contoso Cleaning Services BV"}),
        "require_po": True,
        "active": True,
    }
    return AutoApproveRule(**{**defaults, **overrides})


# --- the citation check -------------------------------------------------


def test_verbatim_citation_passes():
    assert check_citations(_decision(), [CLAUSE]).grounding_passed


def test_citing_a_clause_that_was_not_offered_fails():
    result = check_citations(
        _decision(citations=[PolicyCitation(index=1, clause_id="clause-9", excerpt="anything")]),
        [CLAUSE],
    )
    assert not result.grounding_passed
    assert "not offered" in result.grounding_failure


def test_paraphrased_excerpt_fails():
    result = check_citations(
        _decision(
            citations=[
                PolicyCitation(
                    index=1,
                    clause_id="clause-3",
                    excerpt="the cost centre owner can sign off amounts below a thousand euro",
                )
            ]
        ),
        [CLAUSE],
    )
    assert not result.grounding_passed
    assert "not verbatim" in result.grounding_failure


def test_marker_without_a_citation_fails():
    result = check_citations(_decision(rationale="Under the limit [1] and also [2]."), [CLAUSE])
    assert not result.grounding_passed
    assert "markers without citations" in result.grounding_failure


@pytest.mark.parametrize(
    "outcome", [Outcome.auto_approve, Outcome.route_for_approval, Outcome.reject]
)
def test_any_acting_outcome_with_no_citations_fails(outcome):
    """`route_for_approval` is a policy claim too. An uncited one is a
    decision with no basis, and a live run produced them about one time in
    four before this check covered it."""
    result = check_citations(
        _decision(outcome=outcome, rationale="Looks fine to me.", citations=[]), [CLAUSE]
    )
    assert not result.grounding_passed
    assert "no citations" in result.grounding_failure


def test_needs_human_without_citations_is_allowed():
    """Declining to decide needs no policy support. That is the point."""
    result = check_citations(
        _decision(outcome=Outcome.needs_human, rationale="The clauses conflict.", citations=[]),
        [CLAUSE],
    )
    assert result.grounding_passed


# --- rail 1: grounding --------------------------------------------------


def test_failed_grounding_becomes_needs_human():
    result = check_citations(
        _decision(citations=[PolicyCitation(index=1, clause_id="clause-9", excerpt="x")]),
        [CLAUSE],
    )
    final = apply_rails(result, _invoice(), [], [], rule=_rule())
    assert final.outcome is Outcome.needs_human
    assert not final.executes_automatically


# --- rail 2: unverified fields ------------------------------------------


def test_unverified_field_forces_review():
    result = check_citations(_decision(), [CLAUSE])
    final = apply_rails(result, _invoice(), ["total_incl_vat"], [], rule=_rule())
    assert final.outcome is Outcome.route_for_approval
    assert any("unverified field" in c for c in final.unmet_conditions)


def test_bad_arithmetic_forces_review():
    result = check_citations(_decision(), [CLAUSE])
    final = apply_rails(result, _invoice(), [], ["line items sum to 1518"], rule=_rule())
    assert final.outcome is Outcome.route_for_approval


# --- rail 3: auto-approve needs an explicit rule ------------------------


def test_auto_approve_needs_an_active_rule():
    result = check_citations(_decision(), [CLAUSE])
    final = apply_rails(result, _invoice(), [], [], rule=_rule(active=False))
    assert final.outcome is Outcome.route_for_approval
    assert final.rule_id is None


def test_auto_approve_with_no_rule_at_all_is_queued():
    result = check_citations(_decision(), [CLAUSE])
    final = apply_rails(result, _invoice(), [], [], rule=None)
    assert final.outcome is Outcome.route_for_approval


def test_rule_permits_auto_approve_when_every_condition_holds():
    result = check_citations(_decision(), [CLAUSE])
    final = apply_rails(result, _invoice(), [], [], rule=_rule())
    assert final.outcome is Outcome.auto_approve
    assert final.rule_id == "cost-centre-owner-limit"
    assert final.executes_automatically


def test_over_the_rule_limit_is_queued():
    result = check_citations(_decision(), [CLAUSE])
    final = apply_rails(result, _invoice(total="12196.80"), [], [], rule=_rule())
    assert final.outcome is Outcome.route_for_approval
    assert any("over the" in c for c in final.unmet_conditions)


def test_supplier_off_the_list_is_queued():
    result = check_citations(_decision(), [CLAUSE])
    final = apply_rails(
        result, _invoice(supplier="Litware Consulting Group BV"), [], [], rule=_rule()
    )
    assert final.outcome is Outcome.route_for_approval


def test_missing_po_is_queued():
    result = check_citations(_decision(), [CLAUSE])
    final = apply_rails(result, _invoice(po=None), [], [], rule=_rule())
    assert final.outcome is Outcome.route_for_approval


def test_rails_never_promote_an_outcome():
    """Nothing in the rails may turn a review into an automatic approval."""
    result = check_citations(
        _decision(outcome=Outcome.route_for_approval, rationale="Needs a head [1]."), [CLAUSE]
    )
    final = apply_rails(result, _invoice(), [], [], rule=_rule())
    assert final.outcome is Outcome.route_for_approval


# --- the corpus ---------------------------------------------------------


def test_corpus_splits_on_headings_and_retrieves():
    corpus = PolicyCorpus.from_markdown(
        "# Policy\n\nPreamble.\n\n## 1. Purchase orders\n\nEvery purchase above EUR 500 "
        "requires a purchase order.\n\n## 2. Currency\n\nInvoices are payable in euro.\n"
    )
    assert [c.ref for c in corpus.clauses] == ["Policy", "1. Purchase orders", "2. Currency"]
    top = corpus.retrieve("purchase order required above 500", top_k=1)
    assert top[0].ref == "1. Purchase orders"
    assert "clause-2" in corpus


# --- the retrieval query ------------------------------------------------


def _corpus():
    from pathlib import Path

    return PolicyCorpus.from_path(
        Path(__file__).resolve().parents[1] / "evals/fixtures/procurement-policy.md"
    )


def test_non_euro_invoice_retrieves_the_currency_clause():
    """The M1 spike missed this: a USD invoice never retrieved clause 8,
    because the clause says 'euro' and the invoice says 'USD'."""
    from app.decisions.decide import invoice_query

    invoice = _invoice()
    invoice.currency = _field("USD")
    retrieved = _corpus().retrieve(invoice_query(invoice), top_k=8)
    assert any(clause.ref.startswith("8.") for clause in retrieved)


def test_standing_dimensions_are_always_asked():
    """Threshold, supplier list and PO clauses come back for any invoice."""
    from app.decisions.decide import invoice_query

    refs = [c.ref for c in _corpus().retrieve(invoice_query(_invoice()), top_k=8)]
    assert any(r.startswith("2.") for r in refs)  # purchase orders
    assert any(r.startswith("3.") for r in refs)  # spend thresholds
    assert any(r.startswith("4.") for r in refs)  # approved suppliers


# --- how a clause is identified to the model ----------------------------


def test_a_citation_may_name_the_label_the_id_or_the_source():
    """Resolve leniently, verify strictly.

    The database path hands the model chunk UUIDs. Asking it to copy one of
    seventeen 36-character hex strings back exactly produced citations that
    quoted the right words under the wrong id. Turn-local labels fixed that
    and the model then cited the human-readable source line instead, because
    the render put both in front of it.

    All three resolve. The check that matters is the verbatim one.
    """
    excerpt = "Up to EUR 1,000: the cost centre owner may approve."
    for handle in ("clause-1", CLAUSE.id, CLAUSE.ref):
        result = check_citations(
            _decision(citations=[PolicyCitation(index=1, clause_id=handle, excerpt=excerpt)]),
            [CLAUSE],
            labels={"clause-1": CLAUSE},
        )
        assert result.grounding_passed, f"{handle!r} did not resolve"


def test_a_wrong_quote_still_fails_however_the_clause_was_named():
    """Lenient on the handle must not mean lenient on the words."""
    result = check_citations(
        _decision(
            citations=[
                PolicyCitation(
                    index=1, clause_id="clause-1", excerpt="a sentence from a different clause"
                )
            ]
        ),
        [CLAUSE],
        labels={"clause-1": CLAUSE},
    )
    assert not result.grounding_passed
    assert "not verbatim" in result.grounding_failure


def test_the_render_puts_the_id_on_its_own_line():
    """Side by side, the source line reads like another identifier."""
    block = CLAUSE.cite_block("clause-1")
    assert block.startswith("[clause-1]\n")
    assert "source: " in block


def test_a_heading_inside_a_clause_resolves_to_that_clause():
    """Chunks span several headings; `ref` names only the first. A model
    quoting under "6. Proseware Print & Signage BV" is naming a real heading
    inside a clause it was given, not inventing one."""
    multi = PolicyClause(
        id="chunk-x",
        ref="approved-suppliers.md, 5. Woodgrove Legal BV",
        text=(
            "## 5. Woodgrove Legal BV\n\nApproved for legal services.\n\n"
            "## 6. Proseware Print & Signage BV\n\nApproved for marketing and print."
        ),
    )
    result = check_citations(
        _decision(
            citations=[
                PolicyCitation(
                    index=1,
                    clause_id="6. Proseware Print & Signage BV",
                    excerpt="Approved for marketing and print.",
                )
            ]
        ),
        [multi],
        labels={"clause-1": multi},
    )
    assert result.grounding_passed


def test_a_heading_that_matches_nothing_still_fails():
    result = check_citations(
        _decision(
            citations=[
                PolicyCitation(index=1, clause_id="99. A Supplier We Never Saw", excerpt="x")
            ]
        ),
        [CLAUSE],
        labels={"clause-1": CLAUSE},
    )
    assert not result.grounding_passed


def test_an_ambiguous_heading_is_not_guessed():
    """Two clauses containing the same heading text is not a resolution."""
    a = PolicyClause(id="a", ref="doc.md, One", text="## Currency\n\nPayable in euro.")
    b = PolicyClause(id="b", ref="doc.md, Two", text="## Currency\n\nSomething else.")
    result = check_citations(
        _decision(citations=[PolicyCitation(index=1, clause_id="Currency", excerpt="x")]),
        [a, b],
    )
    assert not result.grounding_passed
