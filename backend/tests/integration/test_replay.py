"""Counterfactual replay: what a rule that does not exist yet would have done.

The claim is narrow and has to stay narrow. Rail 3 is deterministic, and
every input it reads is stored, so the rails can be re-run over decided
history exactly. Nothing here re-runs a model, and nothing here claims to
know what a model would have proposed under a different policy.

The load-bearing test is `test_replaying_the_current_rule_reproduces_history`.
Everything else in this file is only worth reading if that one passes: a
replay is trustworthy exactly insofar as replaying what actually happened
returns what actually happened.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models import (
    Collection,
    Decision,
    DecisionCitation,
    DocumentChunk,
    Extraction,
    SourceDocument,
)
from app.decisions.models import Outcome
from app.decisions.replay import exposure, replay, rule_from_conditions, sweep
from app.extraction.provenance import ExtractedField
from app.extraction.schemas.invoice import Invoice, LineItem
from tests.integration.conftest import _purge

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    from app.db.engine import SessionLocal

    with SessionLocal() as session:
        yield session
        session.rollback()


@pytest.fixture
def user(db):
    from app.db.models import User

    row = User(
        id=uuid.uuid4(),
        email=f"replay-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(row)
    db.commit()
    yield row
    _purge(db, row)


@pytest.fixture
def org(db, user):
    from app.auth.orgs import ensure_personal_org

    return ensure_personal_org(db, user.id, user.email).org_id


def _f(value):
    return ExtractedField(value=value, source_span=str(value))


def _invoice(total="850.00", supplier="Contoso Cleaning Services BV", po="PO-2026-0088"):
    return Invoice(
        supplier=_f(supplier),
        invoice_number=_f(f"INV-{uuid.uuid4().hex[:6]}"),
        total_incl_vat=_f(Decimal(total)),
        vat_amount=_f(Decimal("0.00")),
        currency=_f("EUR"),
        issued_on=_f(date(2026, 2, 12)),
        due_on=_f(date(2026, 3, 14)),
        po_number=_f(po) if po else None,
        line_items=[
            LineItem(
                description=_f("Office cleaning"),
                quantity=_f(Decimal("1")),
                unit_price=_f(Decimal(total)),
                amount=_f(Decimal(total)),
            )
        ],
    )


def _decide(
    db,
    user,
    org,
    invoice: Invoice,
    outcome: Outcome,
    proposed: Outcome | None = None,
    unverified: list[str] | None = None,
    arithmetic_failures: list[str] | None = None,
    grounding_passed: bool = True,
    coverage_complete: bool | None = True,
) -> Decision:
    """A decision as the pipeline would have written it."""
    doc = SourceDocument(
        user_id=user.id,
        org_id=org,
        collection=Collection.transactional,
        vertical="invoice",
        filename=f"{invoice.invoice_number.value}.md",
        r2_key=f"test/{uuid.uuid4()}",
        content_type="text/markdown",
    )
    db.add(doc)
    db.flush()

    import json

    extraction = Extraction(
        org_id=org,
        document_id=doc.id,
        schema_name="invoice",
        document_text="(parsed invoice)",
        fields=json.loads(invoice.model_dump_json()),
        unverified_fields=unverified or [],
        arithmetic_ok=not arithmetic_failures,
        arithmetic_failures=arithmetic_failures or [],
        model="test",
    )
    db.add(extraction)
    db.flush()

    row = Decision(
        org_id=org,
        user_id=user.id,
        document_id=doc.id,
        extraction_id=extraction.id,
        outcome=str(outcome),
        proposed_outcome=str(proposed if proposed is not None else outcome),
        rationale="Within the threshold [1].",
        grounding_passed=grounding_passed,
        coverage_complete=coverage_complete,
    )
    db.add(row)
    db.commit()
    return row


# --- the test the rest of the file rests on -------------------------------


def test_replaying_the_current_rule_reproduces_history(db, user, org):
    """A replay is trustworthy exactly insofar as replaying what happened
    returns what happened. This is why the module calls `apply_rails` rather
    than reimplementing it: a second implementation would be free to drift,
    and every answer would look authoritative while being wrong."""
    rule = rule_from_conditions(
        "standing order",
        {
            "max_total_incl_vat": "1000.00",
            "approved_suppliers": ["Contoso Cleaning Services BV"],
            "require_po": True,
        },
    )

    # Each of these is what the rails would really have produced under `rule`.
    _decide(db, user, org, _invoice("850.00"), Outcome.auto_approve)
    _decide(db, user, org, _invoice("2400.00"), Outcome.route_for_approval,
            proposed=Outcome.auto_approve)
    _decide(db, user, org, _invoice("300.00", po=None), Outcome.route_for_approval,
            proposed=Outcome.auto_approve)
    _decide(db, user, org, _invoice("120.00"), Outcome.needs_human,
            proposed=Outcome.auto_approve, grounding_passed=False)
    _decide(db, user, org, _invoice("90.00"), Outcome.reject, proposed=Outcome.reject)

    report = replay(db, org, rule)

    assert report.considered == 5
    assert report.unreplayable == 0
    assert report.flips == []


# --- loosening and tightening --------------------------------------------


def test_raising_the_limit_shows_exactly_what_it_would_let_through(db, user, org):
    """The question a client actually asks, answered from stored facts with
    no model calls."""
    current = rule_from_conditions("standing order", {"max_total_incl_vat": "1000.00"})

    _decide(db, user, org, _invoice("850.00"), Outcome.auto_approve)
    _decide(db, user, org, _invoice("2400.00"), Outcome.route_for_approval,
            proposed=Outcome.auto_approve)
    _decide(db, user, org, _invoice("1800.00"), Outcome.route_for_approval,
            proposed=Outcome.auto_approve)
    _decide(db, user, org, _invoice("9000.00"), Outcome.route_for_approval,
            proposed=Outcome.auto_approve)

    assert replay(db, org, current).flips == []

    wider = rule_from_conditions("proposed", {"max_total_incl_vat": "2500.00"})
    report = replay(db, org, wider)

    assert report.considered == 4
    assert len(report.newly_automatic) == 2
    assert report.value_newly_automatic == Decimal("4200.00")
    assert report.auto_approved_before == 1
    assert report.auto_approved_after == 3
    assert report.automation_rate_before == 0.25
    assert report.automation_rate_after == 0.75
    assert all(f.was == "route_for_approval" for f in report.newly_automatic)


def test_a_wider_limit_still_cannot_loosen_the_other_rails(db, user, org):
    """Rails 1 and 2 do not have a threshold to widen. A decision that failed
    grounding, or carried an unverified field, stays with a human however
    generous the rule is — which is the property that makes it safe to let a
    client move the number at all."""
    _decide(db, user, org, _invoice("400.00"), Outcome.needs_human,
            proposed=Outcome.auto_approve, grounding_passed=False)
    _decide(db, user, org, _invoice("400.00"), Outcome.route_for_approval,
            proposed=Outcome.auto_approve, unverified=["total_incl_vat"])
    _decide(db, user, org, _invoice("400.00"), Outcome.needs_human,
            proposed=Outcome.auto_approve, coverage_complete=False)
    _decide(db, user, org, _invoice("400.00"), Outcome.route_for_approval,
            proposed=Outcome.auto_approve, arithmetic_failures=["VAT does not add up"])

    report = replay(db, org, rule_from_conditions("generous", {"max_total_incl_vat": "999999"}))

    assert report.considered == 4
    assert report.newly_automatic == []
    assert report.auto_approved_after == 0


def test_tightening_shows_what_would_come_back_to_a_human(db, user, org):
    """The replay runs both directions. A client narrowing a rule after an
    incident needs the same answer as one widening it."""
    _decide(db, user, org, _invoice("850.00"), Outcome.auto_approve)
    _decide(db, user, org, _invoice("120.00"), Outcome.auto_approve)

    report = replay(db, org, rule_from_conditions("tighter", {"max_total_incl_vat": "500.00"}))

    assert len(report.newly_reviewed) == 1
    assert report.newly_reviewed[0].was == "auto_approve"
    assert report.newly_reviewed[0].would_be == "route_for_approval"
    assert "over the" in report.newly_reviewed[0].reason


def test_no_rule_is_the_baseline_every_proposal_is_measured_against(db, user, org):
    """`rule=None` is a question, not a missing argument: it is the v1
    default, everything queued, and the number a proposed rule improves on."""
    _decide(db, user, org, _invoice("850.00"), Outcome.auto_approve)
    _decide(db, user, org, _invoice("200.00"), Outcome.auto_approve)

    report = replay(db, org, None)

    assert report.auto_approved_after == 0
    assert len(report.newly_reviewed) == 2
    assert all("No active auto-approve rule" in f.reason for f in report.newly_reviewed)


# --- the limits, reported rather than hidden ------------------------------


def test_a_decision_with_no_recorded_proposal_is_counted_not_guessed(db, user, org):
    """Rows decided before 0011, where the rails fired, cannot be replayed.
    Reporting a flip count over a silently smaller population is the exact
    mistake this project keeps catching in its own numbers."""
    kept = _decide(db, user, org, _invoice("850.00"), Outcome.auto_approve)
    lost = _decide(db, user, org, _invoice("900.00"), Outcome.route_for_approval)
    lost.proposed_outcome = None
    db.commit()

    report = replay(db, org, rule_from_conditions("wide", {"max_total_incl_vat": "5000"}))

    assert report.considered == 1
    assert report.unreplayable == 1
    assert kept.id not in {f.decision_id for f in report.flips}


def test_a_half_configured_rule_approves_nothing(db, user, org):
    """`rule_from_conditions` goes through `from_row` so a rule with no limit
    gets zero rather than infinity. A replay that built the rule its own way
    would answer a question about a rule the system would never run."""
    _decide(db, user, org, _invoice("1.00"), Outcome.route_for_approval,
            proposed=Outcome.auto_approve)

    report = replay(db, org, rule_from_conditions("half configured", {}))

    assert report.auto_approved_after == 0


# --- the honest half of a policy-change question --------------------------


def test_exposure_names_the_decisions_a_clause_is_holding_up(db, user, org):
    """Editing a clause changes what the model would propose, and nothing
    here can know that without asking it again. So this answers the part
    that is a fact — which decisions were reached by citing this text — and
    refuses the rest."""
    policy = SourceDocument(
        user_id=user.id,
        org_id=org,
        collection=Collection.policy,
        filename="procurement-policy.md",
        r2_key=f"test/{uuid.uuid4()}",
        content_type="text/markdown",
    )
    db.add(policy)
    db.flush()
    chunk = DocumentChunk(
        document_id=policy.id,
        user_id=user.id,
        org_id=org,
        collection=Collection.policy,
        chunk_index=0,
        content="Up to EUR 1,000: the cost centre owner may approve.",
        embedding=[0.0] * 1024,
    )
    other = DocumentChunk(
        document_id=policy.id,
        user_id=user.id,
        org_id=org,
        collection=Collection.policy,
        chunk_index=1,
        content="Every invoice must carry a purchase order number.",
        embedding=[0.0] * 1024,
    )
    db.add_all([chunk, other])
    db.commit()

    cited = _decide(db, user, org, _invoice("850.00"), Outcome.auto_approve)
    also = _decide(db, user, org, _invoice("400.00"), Outcome.route_for_approval)
    unrelated = _decide(db, user, org, _invoice("120.00"), Outcome.auto_approve)

    for decision in (cited, also):
        db.add(
            DecisionCitation(
                decision_id=decision.id,
                chunk_id=chunk.id,
                document_id=policy.id,
                citation_index=1,
                clause_ref="3. Spend thresholds",
                excerpt="Up to EUR 1,000: the cost centre owner may approve.",
            )
        )
    db.add(
        DecisionCitation(
            decision_id=unrelated.id,
            chunk_id=other.id,
            document_id=policy.id,
            citation_index=1,
            clause_ref="2. Purchase orders",
            excerpt="Every invoice must carry a purchase order number.",
        )
    )
    db.commit()

    found = exposure(db, org, chunk.id)

    assert found.decisions == 2
    assert found.clause_ref == "3. Spend thresholds"
    assert found.amount == Decimal("1250.00")
    assert found.outcomes == {"auto_approve": 1, "route_for_approval": 1}
    assert unrelated.id not in {decision_id for decision_id, _ in found.sample}


# --- the ladder ----------------------------------------------------------


def test_the_sweep_agrees_with_replaying_each_rung_separately(db, user, org):
    """The sweep exists only to avoid scanning the history once per rung. If
    it ever disagrees with the thing it is an optimisation of, it is not an
    optimisation."""
    for total in ("200.00", "800.00", "1500.00", "3000.00", "9000.00"):
        _decide(db, user, org, _invoice(total), Outcome.route_for_approval,
                proposed=Outcome.auto_approve)

    limits = [Decimal("500"), Decimal("1000"), Decimal("2500"), Decimal("10000")]
    considered, unreplayable, points = sweep(db, org, limits)

    assert considered == 5
    assert unreplayable == 0
    for point in points:
        one = replay(
            db, org, rule_from_conditions("x", {"max_total_incl_vat": str(point.limit)})
        )
        assert point.automatic == one.auto_approved_after, point.limit
        assert point.newly_automatic == len(one.newly_automatic), point.limit
        assert point.value_newly_automatic == one.value_newly_automatic, point.limit


def test_the_ladder_is_monotonic_in_the_limit(db, user, org):
    """Raising a ceiling cannot automate fewer decisions. Not a deep truth —
    but it is the shape a client reads off the curve, and if the curve ever
    dips the number they are reading is not the one they think."""
    for total in ("100.00", "700.00", "1200.00", "4000.00"):
        _decide(db, user, org, _invoice(total), Outcome.route_for_approval,
                proposed=Outcome.auto_approve)

    _, _, points = sweep(
        db, org, [Decimal(x) for x in ("50", "500", "1000", "2000", "5000")]
    )
    counts = [p.automatic for p in points]
    assert counts == sorted(counts)
    assert counts[0] == 0 and counts[-1] == 4


# --- the statistic the demo leads with ------------------------------------


def test_auto_approved_counts_the_outcome_not_a_rule_id(db, user, org):
    """`/decisions/stats` reports an auto-approved share, and it used to
    count rows carrying a `rule_id`. That is a fair proxy in real data and a
    wrong one the moment anything else writes to the column — which the
    volume fixtures did, as a purge tag, making the demo's headline metric
    read 100% when the true figure was zero."""
    from app.db.models import Decision as DecisionRow

    tagged = _decide(db, user, org, _invoice("400.00"), Outcome.route_for_approval)
    tagged.rule_id = "some-fixture-tag"
    db.commit()

    automatic = db.scalar(
        select(func.count())
        .select_from(DecisionRow)
        .where(DecisionRow.org_id == org, DecisionRow.outcome == str(Outcome.auto_approve))
    )
    tagged_rows = db.scalar(
        select(func.count())
        .select_from(DecisionRow)
        .where(DecisionRow.org_id == org, DecisionRow.rule_id.is_not(None))
    )
    assert automatic == 0
    assert tagged_rows == 1
