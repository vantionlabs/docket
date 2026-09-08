"""Can the configured model actually do what this pipeline needs?

    uv run python scripts/check_model.py

Switching provider is a config change, which makes it easy to point the app
at a model that chats beautifully and cannot hold a schema. This pipeline
does not generate prose. It needs four things, and a model that fails any of
them will not merely score worse: it will fail validation and send every
case to a human.

  1. Structured output      return a typed object, not JSON in a code fence
  2. Closed enums           pick from four outcomes and invent no fifth
  3. Verbatim quoting       copy a span character for character
  4. Judgement both ways    accept a clause that supports a claim, and
                            reject one on a different subject

The judge is exercised through the app's own `judge_citations`, not a
simplified prompt written for this script. A check that invents its own
wording measures a strawman.

Six calls against CHAT_MODEL and GROUNDING_MODEL. Run it after any change to
LLM_PROVIDER, CHAT_MODEL or GROUNDING_MODEL, before the eval and before
trusting a number.
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_ai import Agent  # noqa: E402

from app.config import settings  # noqa: E402
from app.decisions.models import Decision, Outcome  # noqa: E402
from app.extraction.provenance import verify  # noqa: E402
from app.extraction.schemas.invoice import Invoice  # noqa: E402
from app.grounding.verbatim import contains_verbatim  # noqa: E402
from app.llm.providers import chat_model  # noqa: E402

DOCUMENT = """# INVOICE

**Contoso Cleaning Services BV**

| Invoice number | CCS-2026-0411 |
| Invoice date | 12 February 2026 |
| Purchase order | PO-2026-0088 |

| Office cleaning, January 2026 | 1 | 620.00 | 620.00 |

Subtotal excluding VAT: EUR 620.00
VAT: EUR 130.20
**Total including VAT: EUR 750.20**
"""

CLAUSE = "Up to EUR 1,000: the cost centre owner may approve."


def _check(name: str, requirement: str, passed: bool, detail: str = "") -> bool:
    """`detail` explains a failure. It is not printed on a pass, where it
    would read like a complaint about something that worked."""
    print(f"  [{'pass' if passed else 'FAIL'}] {name:26} {requirement}")
    if detail and not passed:
        print(f"         {detail}")
    return passed


def main() -> int:
    print(
        f"provider: {settings.llm_provider}\n"
        f"  chat:      {settings.chat_model}\n"
        f"  grounding: {settings.grounding_model}\n"
    )
    results: list[bool] = []

    # 1 + 3. Typed extraction with verbatim spans.
    try:
        from app.extraction.extract import extract

        result = extract(DOCUMENT, Invoice)
        results.append(
            _check(
                "structured output",
                "returns a typed Invoice",
                isinstance(result.data, Invoice),
            )
        )
        unverified = verify(result.data, DOCUMENT).unverified
        results.append(
            _check(
                "verbatim spans",
                "every source_span is really in the document",
                not unverified,
                f"unverified: {unverified}" if unverified else "",
            )
        )
        results.append(
            _check(
                "reads numbers",
                "total_incl_vat is 750.20",
                result.data.total_incl_vat.value == Decimal("750.20"),
                f"read {result.data.total_incl_vat.value} instead",
            )
        )
    except Exception as exc:
        results.append(_check("structured output", "returns a typed Invoice", False, str(exc)[:90]))

    # 2. Closed enum plus citations.
    try:
        agent = Agent(
            chat_model(),
            output_type=Decision,
            instructions=(
                "Decide using only the clause given. Cite it as clause-1 with a "
                "verbatim excerpt and a [1] marker in the rationale."
            ),
        )
        decision = agent.run_sync(
            f"CLAUSE (clause-1):\n{CLAUSE}\n\nINVOICE total: EUR 750.20"
        ).output
        results.append(
            _check("closed enum", "picks a valid Outcome", decision.outcome in set(Outcome))
        )
        excerpt = decision.citations[0].excerpt if decision.citations else ""
        results.append(
            _check(
                "verbatim citations",
                "quotes the clause exactly",
                bool(excerpt) and contains_verbatim(excerpt, CLAUSE),
                f"got {excerpt!r}" if excerpt else "no citation returned",
            )
        )
    except Exception as exc:
        results.append(_check("closed enum", "picks a valid Outcome", False, str(exc)[:90]))

    # 4 + 5. The judge, exercised through the app's own judge, not a toy
    # version of it. A check that invents its own prompt tests a strawman:
    # the real _JUDGE_PROMPT is specific about what counts as support, and
    # a model's behaviour under it is the only thing that matters here.
    try:
        from app.decisions.decide import judge_citations
        from app.decisions.policy import PolicyClause

        clause = PolicyClause(id="clause-1", ref="3. Spend thresholds", text=CLAUSE)

        rejected = judge_citations(
            "The cost centre owner may approve this invoice [1].",
            [(1, clause, CLAUSE)],
        )
        results.append(
            _check(
                "judge accepts",
                "accepts a clause that does support the claim",
                rejected == [],
                "rejected a citation that plainly supports its claim",
            )
        )

        rejected = judge_citations(
            "This invoice is denominated in US dollars rather than euro [1].",
            [(1, clause, CLAUSE)],
        )
        results.append(
            _check(
                "judge refuses",
                "rejects a clause on a different subject",
                rejected == [1],
                "accepted a spend-threshold clause as supporting a currency claim",
            )
        )
    except Exception as exc:
        results.append(_check("judge", "runs at all", False, str(exc)[:90]))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    if passed < len(results):
        print(
            "\nThis model is not safe for the decision pipeline as configured.\n"
            "A failure here means validation failures and universal escalation,\n"
            "not a slightly worse score. Try a stronger model for the failing\n"
            "role: CHAT_MODEL drives extraction and decisions, GROUNDING_MODEL\n"
            "drives the judge."
        )
        return 1
    print("Safe to run the eval against.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
