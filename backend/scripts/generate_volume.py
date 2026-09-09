"""Bulk decision rows for UI, pagination and query testing. No model calls.

    uv run python scripts/generate_volume.py --count 5000

Fills `decisions`, `extractions`, `decision_citations` and `executions` with
realistic rows so the queue, the audit log and the CSV export can be
exercised at a size where a missing index or an N+1 actually shows up. The
five seeded invoices tell you nothing about what `/audit` does over a year.

**These rows were never decided by the pipeline.** They are shaped like real
decisions and no model produced them, which is exactly what you want for
load testing and exactly what you must not use for evaluating quality. They
are tagged `rule_id='volume-fixture'` so they are trivially separable, and
`--purge` removes them.
"""

import argparse
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.auth.orgs import ensure_personal_org  # noqa: E402
from app.db.engine import SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Collection,
    Decision,
    DecisionCitation,
    DecisionStatus,
    DocumentStatus,
    Execution,
    ExecutionStatus,
    Extraction,
    SourceDocument,
    User,
)
from evals.factories import build_invoices  # noqa: E402

# Fixtures are identified by the R2 key prefix they already carry, not by
# a marker written into a domain column. `rule_id` used to hold this, and
# `rule_id` means "a rule authorised this auto-approval" — so every fixture
# row counted as auto-approved and the demo's headline metric read 100%
# when the true figure was zero. A fixture that has to lie about the data to
# be findable is a fixture that will eventually be believed.
MARKER = "volume/"
FIXTURE_MODEL = "volume-fixture"
DEMO_EMAIL = "demo@northwind.nl"

# How often a decision fails grounding regardless of what the invoice says.
# The M5 baseline measured 33 of 99 grounded, so a third is generous rather
# than pessimistic; the fixtures should not look better than the real thing.
GROUNDING_FAILURE_RATE = 0.12


def _outcomes(scenario, rng) -> tuple[str, str, bool, DecisionStatus]:
    """(proposed, final, grounded, status) for one fixture, coherently.

    The proposal is the scenario's own expected outcome — that is what the
    label means. The final outcome is what the rails do to it with no rule
    configured, which is the demo org's actual state: rail 3 has nothing to
    authorise an automatic approval, so a proposed `auto_approve` queues.

    Deriving the two separately is the point. An earlier version assigned a
    final outcome from a fixed population and set the proposal equal to it,
    which made the fixtures internally incoherent — a clean invoice stored
    as `reject` — and made the loosening direction unreachable: no rule
    could ever release a decision whose proposal was already the outcome.
    """
    proposed = scenario.expected

    if rng.random() < GROUNDING_FAILURE_RATE:
        return proposed, "needs_human", False, DecisionStatus.pending_review

    if proposed == "auto_approve":
        # Rail 3 with no active rule. This is the population a proposed rule
        # is asking about, and there is no point in fixtures without it.
        final = "route_for_approval"
    else:
        final = proposed

    if final == "reject":
        return proposed, final, True, DecisionStatus.rejected
    status = rng.choice(
        [DecisionStatus.executed] * 3 + [DecisionStatus.pending_review] * 2
    )
    return proposed, final, True, status


def purge(db) -> int:
    """Remove the fixture rows and the documents they hang off."""
    doc_ids = list(
        db.scalars(select(SourceDocument.id).where(SourceDocument.r2_key.startswith(MARKER)))
    )
    if not doc_ids:
        return 0
    # Decisions, extractions, citations and executions all cascade from the
    # document, so one delete is enough.
    db.execute(delete(SourceDocument).where(SourceDocument.id.in_(doc_ids)))
    db.commit()
    return len(doc_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--purge", action="store_true", help="remove fixture rows and exit")
    parser.add_argument("--days", type=int, default=365, help="spread over this many days")
    args = parser.parse_args()

    rng = random.Random(23)

    with SessionLocal() as db:
        if args.purge:
            print(f"purged {purge(db)} fixture documents and everything hanging off them")
            return 0

        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            raise SystemExit(
                f"No {DEMO_EMAIL}. Run scripts/seed_demo.py first so there is an org to "
                "attach these to."
            )
        org_id = ensure_personal_org(db, user.id, user.email).org_id

        invoices = build_invoices(args.count, seed=29)
        now = datetime.now(UTC)
        written = 0

        # Batched: 5,000 rows one commit at a time takes minutes and teaches
        # you nothing about the app.
        for start in range(0, len(invoices), 250):
            batch = invoices[start : start + 250]
            for invoice in batch:
                created = now - timedelta(
                    days=rng.uniform(0, args.days), seconds=rng.uniform(0, 86400)
                )
                proposed, outcome, grounded, status = _outcomes(invoice.scenario, rng)

                document = SourceDocument(
                    user_id=user.id,
                    org_id=org_id,
                    collection=Collection.transactional,
                    filename=invoice.filename,
                    r2_key=f"volume/{uuid.uuid4()}",
                    content_type="text/markdown",
                    status=DocumentStatus.ready,
                    created_at=created,
                )
                db.add(document)
                db.flush()

                extraction = Extraction(
                    org_id=org_id,
                    document_id=document.id,
                    schema_name="invoice",
                    document_text=invoice.markdown,
                    # The complete schema, not the four fields a list view
                    # happens to render. A fixture that cannot be validated
                    # back into an Invoice is a fixture the replay, the
                    # detail screen and any future analysis all have to skip.
                    fields=invoice.as_extraction_fields(),
                    unverified_fields=[],
                    checks_ok="arithmetic" not in invoice.scenario.key,
                    check_failures=[],
                    model=FIXTURE_MODEL,
                    created_at=created,
                )
                db.add(extraction)
                db.flush()

                decision = Decision(
                    org_id=org_id,
                    user_id=user.id,
                    document_id=document.id,
                    extraction_id=extraction.id,
                    outcome=outcome,
                    rationale=invoice.scenario.note,
                    unmet_conditions=[invoice.scenario.note],
                    rail_notes=[],
                    # No rule is configured for the demo org, so nothing
                    # authorised an automatic approval. Saying otherwise here
                    # is what broke the auto-approved statistic.
                    rule_id=None,
                    proposed_outcome=proposed,
                    coverage_complete=grounded,
                    grounding_passed=grounded,
                    status=status,
                    assigned_to=rng.choice(["FAC-01", "OPS-04", "IT-01", None]),
                    created_at=created,
                    decided_at=created,
                    reviewed_by=user.id if status is not DecisionStatus.pending_review else None,
                    reviewed_at=(
                        created + timedelta(hours=rng.uniform(1, 72))
                        if status is not DecisionStatus.pending_review
                        else None
                    ),
                )
                db.add(decision)
                db.flush()

                for citation_index in range(1, rng.randint(2, 5)):
                    db.add(
                        DecisionCitation(
                            decision_id=decision.id,
                            citation_index=citation_index,
                            clause_ref=f"procurement-policy.md, {citation_index}. Clause",
                            excerpt="Approval authority is set by the total amount.",
                        )
                    )

                if status is DecisionStatus.executed:
                    db.add(
                        Execution(
                            org_id=org_id,
                            decision_id=decision.id,
                            adapter="dry_run",
                            idempotency_key=f"decision:{decision.id}:approve_for_payment",
                            status=ExecutionStatus.succeeded,
                            response={"external_reference": f"dry-run-{decision.id}"},
                            created_at=created,
                            completed_at=created + timedelta(seconds=rng.uniform(1, 30)),
                        )
                    )
                written += 1

            db.commit()
            print(f"  {written}/{len(invoices)}")

        pending = db.scalar(
            select(Decision)
            .join(SourceDocument, Decision.document_id == SourceDocument.id)
            .where(
                SourceDocument.r2_key.startswith(MARKER),
                Decision.status == DecisionStatus.pending_review,
            )
        )
        print(
            f"\nwrote {written} decisions spread over {args.days} days, "
            f"identified by the {MARKER!r} R2 key prefix"
        )
        print(f"queue now has pending rows: {'yes' if pending else 'no'}")
        print("remove them with: uv run python scripts/generate_volume.py --purge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
