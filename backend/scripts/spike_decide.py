"""M1, the spike (spec section 16). One document in, one decision out.

No app, no queue, no database. This exists to answer the only question
worth paying for early: does extraction with source spans, plus a policy
check, hold up on real documents? If the spans do not verify, stop and
rethink before building a queue on top.

    uv run python scripts/spike_decide.py evals/fixtures/invoices/*.md

Needs a working LLM provider in `.env` (LLM_PROVIDER + the matching key).
PDFs need the docling extra: `uv sync --extra docling`.
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.decisions.decide import decide_invoice  # noqa: E402
from app.decisions.policy import PolicyCorpus  # noqa: E402
from app.decisions.rails import AutoApproveRule, apply_rails  # noqa: E402
from app.extraction.arithmetic import check_invoice  # noqa: E402
from app.extraction.extract import extract  # noqa: E402
from app.extraction.schemas.invoice import Invoice  # noqa: E402
from app.ingestion.parsing import parse_document  # noqa: E402

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "evals/fixtures/procurement-policy.md"

# The rule of rail 3. Inactive by default, because v1 ships with everything
# queued (spec section 4). Pass --arm to see what auto-approve would do.
COST_CENTRE_RULE = AutoApproveRule(
    name="cost-centre-owner-limit",
    max_total_incl_vat=Decimal("1000"),
    approved_suppliers=frozenset(
        {
            "Contoso Cleaning Services BV",
            "Fabrikam Office Supplies BV",
            "Northwind IT Partners BV",
            "Tailspin Facilities BV",
            "Woodgrove Legal BV",
        }
    ),
    require_po=True,
    active=False,
)

_CONTENT_TYPES = {".pdf": "application/pdf", ".md": "text/markdown", ".txt": "text/plain"}


def _rule(arm: bool) -> AutoApproveRule:
    if not arm:
        return COST_CENTRE_RULE
    armed = AutoApproveRule(**vars(COST_CENTRE_RULE))
    armed.active = True
    return armed


def run(path: Path, corpus: PolicyCorpus, rule: AutoApproveRule) -> bool:
    print(f"\n{'=' * 72}\n{path.name}\n{'=' * 72}")

    text = parse_document(
        path.read_bytes(),
        _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        path.name,
    )

    extraction = extract(text, Invoice)
    invoice = extraction.data

    print("\nEXTRACTED")
    print(f"  supplier          {invoice.supplier.value}")
    print(f"  invoice number    {invoice.invoice_number.value}")
    print(f"  total incl VAT    {invoice.total_incl_vat.value} {invoice.currency.value}")
    print(f"  VAT               {invoice.vat_amount.value}")
    print(f"  PO                {invoice.po_number.value if invoice.po_number else 'none'}")
    print(f"  line items        {len(invoice.line_items)}")

    unverified = extraction.unverified_fields
    print(f"\nSPAN CHECK        {'all spans verbatim' if not unverified else 'FAILED'}")
    for name in unverified:
        print(f"  unverified: {name}")

    arithmetic = check_invoice(invoice)
    print(f"ARITHMETIC        {'ok' if arithmetic.ok else 'FAILED'}")
    for failure in arithmetic.failures:
        print(f"  {failure}")

    result = decide_invoice(
        invoice,
        corpus,
        arithmetic_failures=arithmetic.failures,
        unverified_fields=unverified,
    )
    final = apply_rails(result, invoice, unverified, arithmetic.failures, rule=rule)

    print(f"\nPROPOSED          {result.decision.outcome}")
    print(f"GROUNDING         {'passed' if result.grounding_passed else result.grounding_failure}")
    print(f"FINAL             {final.outcome}")
    if final.rule_id:
        print(f"  authorised by rule {final.rule_id!r}")
    if final.assignee_hint:
        print(f"  assign to         {final.assignee_hint}")

    print("\nRATIONALE")
    for line in result.decision.rationale.splitlines():
        print(f"  {line}")

    if final.citations:
        print("\nCITATIONS")
        for index, ref, excerpt in final.citations:
            print(f"  [{index}] {ref}")
            print(f'      "{excerpt}"')

    if final.unmet_conditions:
        print("\nUNMET CONDITIONS")
        for condition in final.unmet_conditions:
            print(f"  - {condition}")

    if final.rail_notes:
        print("\nRAILS")
        for note in final.rail_notes:
            print(f"  - {note}")

    return not unverified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documents", nargs="+", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument(
        "--arm",
        action="store_true",
        help="activate the auto-approve rule, to see what rail 3 would let through",
    )
    args = parser.parse_args()

    corpus = PolicyCorpus.from_path(args.policy)
    print(f"policy: {args.policy.name}, {len(corpus.clauses)} clauses")

    rule = _rule(args.arm)
    spans_held = [run(path, corpus, rule) for path in args.documents]

    print(f"\n{'=' * 72}")
    verified = sum(spans_held)
    print(f"spans verified on {verified}/{len(spans_held)} documents")
    if verified < len(spans_held):
        print("Spans did not verify everywhere. That is the M1 question; read section 17.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
