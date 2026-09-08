"""Decision eval: the two error types, and retrieval recall (spec section 13).

The template's `run_eval.py` scores a chat pipeline. This scores decisions,
and it scores the two failure modes separately because they are not the
same thing:

  false auto-approve   money out the door, unrecoverable trust.  GATE: zero.
  false escalation     somebody clicks a button.                 COST: report.

CI gates on false auto-approves at zero. False escalations are a number,
not a gate: they set the ROI, and the whole tuning loop is lowering them
while the first stays at zero. A harness that gated both would be tuned by
making the system approve more, which is exactly backwards.

**The eval MUST run with an armed rule.** Rail 3 means nothing auto-approves
unless a rule says it may, so an eval that passes no rule makes
`auto_approve` unreachable, and then "zero false auto-approves" is true
because the system is incapable of the failure rather than because it
avoids it. The first version of this harness did exactly that and reported
a confident, meaningless PASS. The rule below is the one the gate is
actually testing; change it and you are testing something else.

**Retrieval recall is a first-class metric here**, not a diagnostic. The M1
spike found a decision that was confidently wrong because a clause was never
retrieved, and no downstream check can see that: the verbatim check, the
judge and the reviewer all inspect what came back. So recall is measured per
decision, against the obligations the document actually triggers.

    uv run python evals/run_decision_eval.py --live --dataset evals/decisions-train.jsonl
    uv run python evals/run_decision_eval.py --dataset evals/decisions.jsonl

**Use `--live` for anything you intend to act on.** Without it the eval
builds an in-memory corpus from one markdown file and retrieves lexically,
which is not the pipeline that runs in production: no embeddings, no
distractor documents, and obligations extracted fresh rather than the
scoped ones in the database. Tuning against that measures a different
system and the improvement will not transfer. The file mode stays because
it needs no database and is useful for a quick structural check.

Exits non-zero on any false auto-approve, or if recall falls below
--min-recall.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0].parent))

from sqlalchemy import func  # noqa: E402

from app.decisions.coverage import (  # noqa: E402
    CoverageReport,
    check_coverage,
    subject_terms,
    triggered_dimensions,
)
from app.decisions.decide import decide_invoice  # noqa: E402
from app.decisions.models import Outcome  # noqa: E402
from app.decisions.policy import CoveredPolicy, PolicyCorpus  # noqa: E402
from app.decisions.rails import AutoApproveRule, apply_rails  # noqa: E402
from app.extraction.arithmetic import check_invoice  # noqa: E402
from app.extraction.extract import extract  # noqa: E402
from app.extraction.schemas.invoice import Invoice  # noqa: E402
from app.ingestion.parsing import parse_document  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_DATASET = Path(__file__).resolve().parent / "decisions.jsonl"

# Outcomes that mean "a person looks at this".
ESCALATIONS = {Outcome.route_for_approval, Outcome.needs_human}

# The rule under test. Without one, rail 3 blocks every auto-approve and the
# gate cannot fail. This mirrors a real cost-centre-owner delegation.
EVAL_RULE = AutoApproveRule(
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
    active=True,
)


@dataclass
class Case:
    document: str
    expected: str
    """The outcome a human actually reached. `auto_approve` means it was
    safe to pay without review, not that the pipeline should be confident."""
    must_cite_dimensions: list[str] = field(default_factory=list)
    """Dimensions whose rules a correct decision has to have considered.
    This is what turns "did it answer well" into "did it ask everything"."""
    note: str = ""


@dataclass
class Result:
    case: Case
    actual: str
    recall: float
    missed: list[str]
    grounded: bool
    error: str = ""
    """Set when the case could not be run at all. An eval that dies on one
    flaky response is an eval nobody finishes, and a 99-case run that
    aborts at case 40 has spent the money and produced nothing."""

    @property
    def false_auto_approve(self) -> bool:
        """Approved without review something a human did not approve.

        A case that errored is never a false auto-approve: nothing was
        approved. It is counted separately so an error can never quietly
        satisfy the gate.
        """
        if self.error:
            return False
        return self.actual == Outcome.auto_approve and self.case.expected != "auto_approve"

    @property
    def false_escalation(self) -> bool:
        """Queued something a human would have let through."""
        return self.case.expected == "auto_approve" and self.actual in ESCALATIONS

    @property
    def outcome_matches(self) -> bool:
        return self.actual == self.case.expected


def load_cases(path: Path) -> list[Case]:
    if not path.exists():
        raise SystemExit(
            f"No dataset at {path}. Write one: a JSONL file of "
            '{"document": "...", "expected": "...", "must_cite_dimensions": [...]}'
        )
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            cases.append(Case(**json.loads(line)))
    return cases


def run_case(case: Case, corpus, obligations: list) -> Result:
    path = FIXTURES / case.document
    text = parse_document(path.read_bytes(), "text/markdown", path.name)

    extraction = extract(text, Invoice)
    invoice = extraction.data
    arithmetic = check_invoice(invoice)

    triggered = triggered_dimensions(invoice, arithmetic_ok=arithmetic.ok)
    source = CoveredPolicy(
        corpus,
        obligations=obligations,
        triggered=triggered,
        terms=subject_terms(invoice),
    )

    result = decide_invoice(
        invoice,
        source,
        arithmetic_failures=arithmetic.failures,
        unverified_fields=extraction.unverified_fields,
    )
    final = apply_rails(
        result, invoice, extraction.unverified_fields, arithmetic.failures, rule=EVAL_RULE
    )

    # Recall is measured against what the case says had to be considered,
    # falling back to whatever the document triggered. Stating it per case
    # is what makes a regression legible: "the currency rule stopped being
    # retrieved" beats "recall dropped to 0.8".
    if case.must_cite_dimensions:
        required = {d for d in triggered if str(d) in case.must_cite_dimensions}
        report = check_coverage(
            obligations, required, {c.id for c in result.clauses}, subject_terms(invoice)
        )
    else:
        report = result.coverage or CoverageReport()

    return Result(
        case=case,
        actual=str(final.outcome),
        recall=report.recall,
        missed=[o.clause_ref for o in report.missed],
        grounded=final.grounding_passed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--policy", type=Path, default=FIXTURES / "procurement-policy.md")
    parser.add_argument(
        "--min-recall",
        type=float,
        default=1.0,
        help="fail below this mean retrieval recall (default 1.0: miss nothing)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "run against the real pipeline: the corpus in the database, Voyage "
            "embeddings, and the scoped obligations. Needs DATABASE_URL and a "
            "seeded org. Without it the eval measures a different system."
        ),
    )
    parser.add_argument(
        "--email",
        default="demo@northwind.nl",
        help="whose corpus to retrieve against in --live mode",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help=(
            "repeat every case N times and report stability. The pipeline is "
            "not deterministic, so a single run is an anecdote: use this "
            "before concluding a prompt change helped."
        ),
    )
    args = parser.parse_args()

    if not EVAL_RULE.active:
        raise SystemExit(
            "EVAL_RULE is not active, so auto_approve is unreachable and the "
            "false-auto-approve gate cannot fail. Arm it or delete the gate."
        )

    cases = load_cases(args.dataset)

    if args.live:
        corpus, obligations, described = _live_source(args.email)
    else:
        corpus = PolicyCorpus.from_path(args.policy)
        obligations = _obligations_from_corpus(corpus)
        described = f"{args.policy.name} in memory, lexical retrieval"
        print(
            "WARNING: not --live. This measures an in-memory lexical corpus,\n"
            "         not the pipeline that runs in production. Fine for a\n"
            "         structural check; do not tune against it.\n"
        )

    print(
        f"{len(cases)} cases, {described}, "
        f"{len(obligations)} obligations, rule {EVAL_RULE.name!r} armed\n"
    )
    print(f"{'document':34} {'expected':20} {'actual':20} {'recall':>7}  grounded")
    print("-" * 96)

    def _attempt(case: Case) -> Result:
        """Run one case, or record why it could not be run.

        Printed as it lands rather than collected and printed at the end: a
        long run that crashes at case 40 should still show you the first 39.
        """
        try:
            result = run_case(case, corpus, obligations)
        except Exception as exc:  # noqa: BLE001 -- one bad case is not the run
            result = Result(
                case=case,
                actual="error",
                recall=0.0,
                missed=[],
                grounded=False,
                error=f"{type(exc).__name__}: {exc}"[:120],
            )
        flag = " <-- FALSE AUTO-APPROVE" if result.false_auto_approve else ""
        print(
            f"{result.case.document:34} {result.case.expected:20} {result.actual:20} "
            f"{result.recall:7.2f}  {'yes' if result.grounded else 'no ':8}{flag}",
            flush=True,
        )
        if result.error:
            print(f"{'':34} error: {result.error}", flush=True)
        for ref in result.missed:
            print(f"{'':34} missed: {ref}", flush=True)
        return result

    runs: list[list[Result]] = [
        [_attempt(case) for case in cases] for _ in range(args.runs)
    ]
    results = [r for run in runs for r in run]

    if args.runs > 1:
        print(f"\nstability over {args.runs} runs")
        print("-" * 96)
        for index, case in enumerate(cases):
            outcomes = [run[index].actual for run in runs]
            distinct = sorted(set(outcomes))
            agreement = max(outcomes.count(o) for o in distinct) / len(outcomes)
            marker = "  <-- unstable" if len(distinct) > 1 else ""
            print(
                f"{case.document:34} {agreement:5.0%} agreement  "
                f"{', '.join(f'{o}x{outcomes.count(o)}' for o in distinct)}{marker}"
            )

    total = len(results)
    errored = [r for r in results if r.error]
    scored = [r for r in results if not r.error]
    false_auto = [r for r in results if r.false_auto_approve]
    false_esc = [r for r in scored if r.false_escalation]
    mean_recall = (
        sum(r.recall for r in scored) / len(scored) if scored else 1.0
    )
    proposed_auto = any(r.actual == Outcome.auto_approve for r in scored)

    print("\n" + "=" * 96)
    print(f"runs                 {args.runs} x {len(cases)} cases = {total} decisions")
    if errored:
        # Loud, because quality numbers computed over a shrinking
        # denominator look better the more often the pipeline falls over.
        print(f"ERRORED              {len(errored)}/{total}   (excluded from the rates below)")
        from collections import Counter

        for kind, count in Counter(r.error.split(":")[0] for r in errored).most_common():
            print(f"                     {count:>3} x {kind}")
    print(f"outcome matches      {sum(r.outcome_matches for r in scored)}/{len(scored)}")
    print(f"grounded             {sum(r.grounded for r in scored)}/{len(scored)}")
    print(f"mean recall          {mean_recall:.3f}")
    print(f"false escalations    {len(false_esc)}/{len(scored)}   (cost, not a gate)")
    print(f"FALSE AUTO-APPROVES  {len(false_auto)}/{len(scored)}   (gate: must be 0)")

    if not proposed_auto:
        # An honest caveat rather than a green tick. The gate is well formed
        # and nothing exercised it, which is not the same as passing it.
        print(
            "\nNOTE: no decision reached auto_approve in this run, so the "
            "false-auto-approve gate was never exercised. It is armed and "
            "untested, not proven."
        )

    if false_auto:
        print("\nFAIL: a decision was auto-approved that a human did not approve.")
        return 1
    if errored:
        # Not a quality failure, but not a pass either. A run that could not
        # execute part of its own set has not measured what it claims to.
        print(f"\nFAIL: {len(errored)} case(s) could not be run. Fix those first.")
        return 1
    if not scored:
        print("\nFAIL: nothing was scored.")
        return 1
    if mean_recall < args.min_recall:
        print(f"\nFAIL: mean recall {mean_recall:.3f} below --min-recall {args.min_recall}")
        return 1
    print("\nPASS")
    return 0


def _live_source(email: str):
    """The real retrieval path: database corpus, embeddings, scoped obligations.

    Returns (source, obligations, description). The source is the same
    `RetrievedPolicy` the decide workflow builds, so a number from here is a
    number about the system that actually runs.
    """
    from sqlalchemy import select

    from app.auth.orgs import active_membership
    from app.db.engine import SessionLocal
    from app.db.models import Collection, DocumentChunk, SourceDocument, User
    from app.decisions.coverage import load_obligations
    from app.decisions.policy import RetrievedPolicy
    from app.llm.embeddings import embeddings_available

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            raise SystemExit(
                f"No user {email!r}. Run scripts/seed_demo.py first, or pass --email."
            )
        org_id = active_membership(db, user.id, user.email).org_id
        obligations = load_obligations(db, org_id, "invoice")
        documents = list(
            db.scalars(
                select(SourceDocument.filename).where(
                    SourceDocument.org_id == org_id,
                    SourceDocument.collection == Collection.policy,
                )
            )
        )
        chunks = db.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(
                DocumentChunk.org_id == org_id,
                DocumentChunk.collection == Collection.policy,
            )
        )

    if not obligations:
        raise SystemExit(
            "No obligations indexed for this org, so coverage checking is a "
            "no-op and the run would measure retrieval alone. Ingest the policy "
            "corpus first."
        )

    available, reason = embeddings_available()
    mode = "hybrid" if available else f"FTS only ({reason})"
    described = f"{len(documents)} policy documents, {chunks} chunks, {mode}"
    return RetrievedPolicy(user.id), obligations, described


def _obligations_from_corpus(corpus: PolicyCorpus) -> list:
    """Index the fixture corpus in-process, so the eval needs no database.

    Cached to disk beside the dataset: indexing is a model call per clause
    and the corpus does not change between runs, so paying for it every time
    would make the eval something nobody runs.
    """
    from app.decisions.coverage import Dimension, Obligation, extract_obligations

    cache = DEFAULT_DATASET.with_suffix(".obligations.json")
    if cache.exists():
        raw = json.loads(cache.read_text())
    else:
        raw = []
        for clause in corpus.clauses:
            for obligation in extract_obligations(clause.text, clause.ref):
                raw.append({**obligation, "clause_id": clause.id, "clause_ref": clause.ref})
        cache.write_text(json.dumps(raw, indent=2))
        print(f"indexed the corpus into {len(raw)} obligations -> {cache.name}")

    return [
        Obligation(
            id=o["clause_id"],
            dimension=Dimension(o["dimension"]),
            summary=o["summary"],
            clause_ref=o["clause_ref"],
            always_applies=o.get("always_applies", False),
        )
        for o in raw
    ]


if __name__ == "__main__":
    raise SystemExit(main())
