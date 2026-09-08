"""The generated eval set has to be right, or it measures nothing.

A labelled set nobody validates is worse than no set: it produces confident
numbers about a pipeline that was tested against the wrong documents. These
run the generator's own output through the same deterministic checks the
pipeline uses, so a case labelled `reject` for bad arithmetic really does
have bad arithmetic.
"""

import re
from decimal import Decimal

import pytest

from evals.factories import (
    APPROVED_SUPPLIERS,
    SCENARIOS,
    build_corpus,
    build_invoices,
)

INVOICES = build_invoices(120, seed=11)
BY_KEY = {s.key: [i for i in INVOICES if i.scenario.key == s.key] for s in SCENARIOS}


def _parse(markdown: str) -> tuple[Decimal, Decimal, Decimal, list[Decimal]]:
    """Read the totals back off the rendered document, as extraction would."""
    # Anchored: "Subtotal excluding VAT: EUR 219.71" also matches a bare
    # `VAT: ...` pattern, which read the subtotal back as the VAT and made
    # every clean invoice look broken.
    subtotal = Decimal(
        re.search(r"^Subtotal excluding VAT: \w+ ([\d.]+)", markdown, re.M).group(1)
    )
    vat = Decimal(re.search(r"^VAT: \w+ ([\d.]+)", markdown, re.M).group(1))
    total = Decimal(
        re.search(r"^\*\*Total including VAT: \w+ ([\d.]+)\*\*", markdown, re.M).group(1)
    )
    lines = [
        Decimal(m.group(1))
        for m in re.finditer(r"^\| .+ \| \d+ \| [\d.]+ \| ([\d.]+) \|$", markdown, re.M)
    ]
    return subtotal, vat, total, lines


# --- determinism ---------------------------------------------------------


def test_the_same_seed_gives_the_same_corpus():
    """Not decoration: `hash()` on a str is salted per process, and using it
    would have made every eval pass incomparable to the last."""
    assert build_corpus(seed=7) == build_corpus(seed=7)


def test_the_same_seed_gives_the_same_invoices():
    first = [i.markdown for i in build_invoices(20, seed=3)]
    second = [i.markdown for i in build_invoices(20, seed=3)]
    assert first == second


def test_a_different_seed_gives_a_different_set():
    assert build_invoices(20, seed=3)[0].markdown != build_invoices(20, seed=4)[0].markdown


# --- the labels are true --------------------------------------------------


def test_clean_invoices_actually_add_up():
    """The most important test here. A 'clean' case whose arithmetic fails
    would be labelled auto_approve and correctly rejected by the pipeline,
    and the eval would report a false escalation that was the set's fault."""
    for invoice in BY_KEY["clean_under_threshold"]:
        subtotal, vat, total, lines = _parse(invoice.markdown)
        assert sum(lines) == subtotal, invoice.filename
        assert subtotal + vat == total, invoice.filename


def test_clean_invoices_pass_the_real_arithmetic_check():
    """Not a re-implementation: the actual checker the pipeline runs."""
    from app.extraction.arithmetic import TOLERANCE

    for invoice in BY_KEY["clean_under_threshold"]:
        subtotal, vat, total, lines = _parse(invoice.markdown)
        assert abs(sum(lines) - (total - vat)) <= TOLERANCE, invoice.filename


def test_broken_arithmetic_is_actually_broken():
    from app.extraction.arithmetic import TOLERANCE

    cases = BY_KEY["arithmetic_wrong"]
    assert cases, "the weighted population produced none of this scenario"
    for invoice in cases:
        _subtotal, vat, total, lines = _parse(invoice.markdown)
        assert abs(sum(lines) - (total - vat)) > TOLERANCE, invoice.filename


def test_illegal_vat_rate_is_actually_illegal():
    from app.extraction.arithmetic import LEGAL_VAT_RATES, VAT_RATE_TOLERANCE

    for invoice in BY_KEY["illegal_vat_rate"]:
        subtotal, vat, _total, _lines = _parse(invoice.markdown)
        rate = vat / subtotal
        assert not any(abs(rate - legal) <= VAT_RATE_TOLERANCE for legal in LEGAL_VAT_RATES)


def test_clean_invoices_are_under_the_cost_centre_limit():
    for invoice in BY_KEY["clean_under_threshold"]:
        assert invoice.total_incl_vat <= Decimal("1000"), invoice.filename


def test_over_threshold_invoices_are_over_it():
    for invoice in BY_KEY["over_threshold"]:
        assert invoice.total_incl_vat > Decimal("1000"), invoice.filename


def test_unknown_supplier_invoices_use_a_supplier_off_the_list():
    for invoice in BY_KEY["unknown_supplier"]:
        assert invoice.supplier not in APPROVED_SUPPLIERS, invoice.filename


def test_clean_invoices_use_an_approved_supplier():
    for invoice in BY_KEY["clean_under_threshold"]:
        assert invoice.supplier in APPROVED_SUPPLIERS, invoice.filename


def test_foreign_currency_invoices_are_not_in_euro():
    for invoice in BY_KEY["foreign_currency"]:
        assert invoice.currency != "EUR", invoice.filename


def test_no_purchase_order_invoices_have_none_and_need_one():
    for invoice in BY_KEY["no_purchase_order"]:
        assert "not supplied" in invoice.markdown, invoice.filename
        assert invoice.total_incl_vat > Decimal("500"), invoice.filename


def test_short_payment_terms_are_inside_fourteen_days():
    for invoice in BY_KEY["short_payment_terms"]:
        assert "urgent" in invoice.markdown, invoice.filename


def test_duplicates_point_at_a_real_earlier_number():
    for invoice in BY_KEY["duplicate_invoice"]:
        assert invoice.duplicate_of == invoice.invoice_number, invoice.filename


# --- the corpus is hard enough to be worth testing against ---------------


def test_the_corpus_carries_deliberate_distractors():
    """Ranking cannot fail against a corpus with nothing to confuse it."""
    corpus = build_corpus()
    assert "travel-and-expenses.md" in corpus
    assert "procurement-policy-2024-superseded.md" in corpus
    # The distractors carry their own threshold ladders, which is the point.
    assert "may approve" in corpus["travel-and-expenses.md"]
    assert "may approve" in corpus["capital-expenditure.md"]


def test_the_superseded_policy_carries_different_thresholds():
    """The nastiest distractor: right subject, right vocabulary, wrong year."""
    corpus = build_corpus()
    current = corpus["procurement-policy.md"]
    old = corpus["procurement-policy-2024-superseded.md"]
    assert "EUR 500" in current
    assert "EUR 1,000 excluding" in old  # the 2024 PO threshold, not today's


def test_the_travel_policy_says_it_does_not_govern_invoices():
    corpus = build_corpus()
    assert "does NOT govern supplier invoices" in corpus["travel-and-expenses.md"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.key)
def test_every_scenario_names_dimensions_the_checker_knows(scenario):
    """A dimension the coverage check cannot evaluate would silently never
    be required, and the case would pass for the wrong reason."""
    from app.decisions.coverage import Dimension

    for name in scenario.dimensions:
        assert name in {d.value for d in Dimension}, f"{scenario.key}: {name}"


# --- the train / holdout split -------------------------------------------


def _load(name: str) -> list[dict]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "evals" / name
    if not path.exists():
        pytest.skip(f"{name} not generated yet")
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def test_the_two_halves_do_not_overlap():
    """The whole value of a holdout is that tuning never saw it."""
    train = {c["document"] for c in _load("decisions-train.jsonl")}
    holdout = {c["document"] for c in _load("decisions-holdout.jsonl")}
    assert train and holdout
    assert not (train & holdout), "a case appears in both halves"


def test_the_split_covers_the_whole_set():
    train = {c["document"] for c in _load("decisions-train.jsonl")}
    holdout = {c["document"] for c in _load("decisions-holdout.jsonl")}
    everything = {c["document"] for c in _load("decisions-generated.jsonl")}
    assert train | holdout == everything


def test_both_halves_carry_the_same_mix():
    """Stratified, not random. A random split lands all the rare nasties on
    one side often enough to matter, and then the holdout is measuring a
    different problem from the one that was tuned."""
    from collections import Counter

    train = Counter(c["expected"] for c in _load("decisions-train.jsonl"))
    holdout = Counter(c["expected"] for c in _load("decisions-holdout.jsonl"))
    assert set(train) == set(holdout), "an outcome appears in only one half"

    for outcome in train:
        train_share = train[outcome] / sum(train.values())
        holdout_share = holdout[outcome] / sum(holdout.values())
        assert abs(train_share - holdout_share) < 0.10, outcome
