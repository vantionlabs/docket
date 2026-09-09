"""What a rule still stops when the model is wrong (spec sections 13 and 16).

Section 16 says auto-approve is turned on "once the eval set supports it",
and section 13 says the gate is false auto-approves at zero on the labelled
set. Both of those measure the *model*, and both need a model run to answer.
This asks a different question that needs no model at all, and is the one
that decides whether a rule is safe to write down:

    if the model were maximally wrong — if it proposed auto_approve for
    every invoice in the labelled set, including the deliberate nasties —
    which of them would this rule still stop?

That is defence in depth stated as an experiment. A rule whose safety rests
on the model being right is not a gate, it is a formality; the rails exist
precisely because the model is a component that fails. Running the real
rails against the real labelled set under the worst assumption about the
model tells you what the rule is actually worth on its own.

The answer is not "the rule catches everything". It is not supposed to be.
Some nasties are caught in code (arithmetic, VAT), some by the rule
(threshold, purchase order, supplier), and some only by the model reading
the policy (a duplicate, a currency the policy refuses). Knowing which is
which is the point: the third group is where an auto-approve rule is
trusting the model, and that is the group section 13's eval has to cover
before anything is armed.

    uv run python evals/check_rule.py --limit 1000 --require-po
    uv run python evals/check_rule.py --limit 1000 --strict   # CI gate
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.decisions.decide import DecisionResult  # noqa: E402
from app.decisions.models import Decision, Outcome  # noqa: E402
from app.decisions.rails import apply_rails  # noqa: E402
from app.decisions.replay import rule_from_conditions  # noqa: E402
from app.extraction.schemas.invoice import Invoice  # noqa: E402
from app.verticals import get_vertical  # noqa: E402
from evals.factories import SCENARIOS, build_invoices  # noqa: E402

# Scenarios where auto-approval would be a false auto-approve — the error
# section 13 gates at zero, because it is money out of the door.
MUST_NOT_AUTO_APPROVE = {s.key for s in SCENARIOS if s.expected != "auto_approve"}


def worst_case(rule, count: int = 300, seed: int = 11) -> dict[str, dict]:
    """Run the labelled set through the real rails, assuming the model said
    auto_approve for every one of them.

    Nothing is mocked but the model's proposal, and that is mocked to its
    worst possible value rather than a plausible one. Grounding passes and
    coverage is complete, because assuming those failed would let the rule
    take credit for rails that had already stopped the invoice.
    """
    vertical = get_vertical("invoice")
    results: dict[str, dict] = {
        s.key: {"seen": 0, "released": 0, "examples": []} for s in SCENARIOS
    }

    for generated in build_invoices(count, seed=seed):
        invoice = Invoice.model_validate(generated.as_extraction_fields())
        checks = vertical.check(invoice)

        # The pipeline runs one more deterministic check that a single
        # document cannot fail on its own: whether this invoice number has
        # been seen before (`_seen_before` in the decide workflow). Modelling
        # it here rather than ignoring it is the difference between asking
        # what the rule stops and asking what the system stops — and leaving
        # it out would have this script keep reporting a hole that has since
        # been closed in code.
        if generated.duplicate_of:
            checks.failures.append(
                f"invoice {generated.invoice_number} was already extracted "
                "from another document"
            )

        result = DecisionResult(
            decision=Decision(
                outcome=Outcome.auto_approve,
                rationale="(the model is assumed to be wrong)",
                unmet_conditions=[],
            ),
            clauses=[],
            grounding_passed=True,
            coverage=None,
        )
        final = apply_rails(result, invoice, [], checks.failures, rule=rule)

        row = results[generated.scenario.key]
        row["seen"] += 1
        if final.outcome is Outcome.auto_approve:
            row["released"] += 1
            if len(row["examples"]) < 3:
                row["examples"].append(
                    (generated.invoice_number, generated.total_incl_vat, generated.currency)
                )
    return results


def escape_ladder(limits: list[Decimal], require_po: bool, suppliers: list[str],
                  min_payment_days: int = 0, count: int = 300) -> dict[str, Decimal | None]:
    """The lowest limit at which each labelled nasty starts getting through.

    A single limit answers "does this rule stop it", which is the question
    that produces false comfort: at EUR 1,000 the foreign-currency cases are
    all stopped, and it is tempting to read that as the rule understanding
    currency. It does not. Those invoices are generated at EUR 1,000-9,000,
    so they are stopped by the amount, and a cheap foreign-currency invoice
    would walk straight through.

    Running the ladder separates the two. A scenario stopped by a mechanism
    that reads it — arithmetic, purchase order, supplier list — never
    escapes at any limit. A scenario stopped only by its price escapes as
    soon as the limit clears its price, and the ladder says exactly where.
    """
    escapes: dict[str, Decimal | None] = {s.key: None for s in SCENARIOS}
    for limit in sorted(limits):
        rule = rule_from_conditions(
            "ladder",
            {
                "max_total_incl_vat": str(limit),
                "require_po": require_po,
                "approved_suppliers": suppliers,
                "min_payment_days": min_payment_days,
            },
        )
        for key, row in worst_case(rule, count=count).items():
            if row["released"] and escapes[key] is None:
                escapes[key] = limit
    return escapes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", default="1000", help="max_total_incl_vat")
    parser.add_argument("--require-po", action="store_true", default=True)
    parser.add_argument("--no-require-po", dest="require_po", action="store_false")
    parser.add_argument(
        "--approved-suppliers",
        action="store_true",
        help="restrict to the corpus's approved supplier list",
    )
    parser.add_argument(
        "--min-payment-days",
        type=int,
        default=0,
        help="refuse auto-approval when the invoice is due sooner than this",
    )
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if any labelled nasty is released (the CI gate)",
    )
    args = parser.parse_args()

    from evals.factories import APPROVED_SUPPLIERS

    rule = rule_from_conditions(
        "proposed",
        {
            "max_total_incl_vat": args.limit,
            "require_po": args.require_po,
            "approved_suppliers": list(APPROVED_SUPPLIERS) if args.approved_suppliers else [],
            "min_payment_days": args.min_payment_days,
        },
    )

    print(
        f"rule: up to EUR {Decimal(args.limit):,.2f}"
        f"{', PO required' if args.require_po else ', no PO required'}"
        f"{', approved suppliers only' if args.approved_suppliers else ', any supplier'}"
        f"{f', at least {args.min_payment_days} days to pay' if args.min_payment_days else ''}"
    )
    print("assuming the model proposes auto_approve for every invoice.\n")

    results = worst_case(rule, count=args.count)
    escaped: list[str] = []

    header = (
        f"{'labelled scenario':<26}{'correct outcome':<20}"
        f"{'seen':>6}{'released':>10}  stopped by"
    )
    print(header)
    print("-" * 88)
    for scenario in SCENARIOS:
        row = results[scenario.key]
        if not row["seen"]:
            continue
        released = row["released"]
        must_stop = scenario.key in MUST_NOT_AUTO_APPROVE
        if must_stop and released:
            escaped.append(scenario.key)
            stopped = "NOTHING — the rule trusts the model here"
        elif must_stop:
            stopped = "the rails or the rule"
        else:
            stopped = "(correctly released)"

        print(
            f"{scenario.key:<26}{scenario.expected:<20}{row['seen']:>6}{released:>10}  {stopped}"
        )

    print()
    if escaped:
        print("These labelled nasties reach auto_approve when the model is wrong:")
        for key in escaped:
            examples = ", ".join(
                f"{number} ({currency} {total})"
                for number, total, currency in results[key]["examples"]
            )
            print(f"  {key}: {results[key]['released']}/{results[key]['seen']}  e.g. {examples}")
        print(
            "\nThat is not automatically a bug. It means the rule alone does not "
            "stop them,\nso arming it makes the model's judgement load-bearing "
            "for those cases —\nwhich is exactly what section 13's eval has to "
            "measure before anything is armed."
        )
    else:
        print("No labelled nasty reaches auto_approve even with the model assumed wrong.")

    # Which of them were stopped by a mechanism that reads them, and which
    # only by their price.
    ladder = [Decimal(x) for x in ("500", "1000", "2500", "5000", "10000", "25000", "1000000")]
    escapes = escape_ladder(
        ladder,
        args.require_po,
        list(rule.approved_suppliers),
        min_payment_days=args.min_payment_days,
        count=args.count,
    )

    print("\nAt what limit does each labelled nasty start getting through?")
    print(f"{'labelled scenario':<26}{'escapes at':>14}   what that means")
    print("-" * 88)
    for scenario in SCENARIOS:
        if scenario.key not in MUST_NOT_AUTO_APPROVE:
            continue
        at = escapes[scenario.key]
        if at is None:
            meaning = "stopped by something that reads it, at any limit"
            shown = "never"
        elif at <= Decimal(args.limit):
            meaning = "already getting through at the proposed limit"
            shown = f"EUR {at:,.0f}"
        else:
            meaning = "stopped only by its price — raise the limit and it walks through"
            shown = f"EUR {at:,.0f}"
        print(f"{scenario.key:<26}{shown:>14}   {meaning}")

    if escaped and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
