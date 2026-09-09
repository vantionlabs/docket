"""The gate that had never fired (spec sections 9 and 16).

Auto-approve is the only path where money moves without a person, and until
this file nothing had ever driven it end to end. The pieces were each
tested — the rails downgrade correctly, the router only routes an
auto_approve, an execution is idempotent — and no test had ever put an
armed rule in a database and watched a decision travel from proposal to
`executions` row.

That gap is exactly the shape of the ones this project keeps finding: every
component green, the composition never run. The M5 eval had the same hole
from the other side — it passed no rule, so `auto_approve` was unreachable
and "zero false auto-approves out of 99" measured nothing at all.

These tests start after extraction, because extraction and the decision are
model calls and the gate is not. Everything from the rails onward is real:
a real rule row, the real `apply_rails`, the real router, the real event and
the real execute workflow against a real database.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.task_context import TaskContext
from app.db.models import (
    Collection,
    DecisionStatus,
    Execution,
    ExecutionStatus,
    Extraction,
    Rule,
    SourceDocument,
)
from app.decisions.decide import DecisionResult
from app.decisions.models import Decision as ProposedDecision
from app.decisions.models import Outcome
from app.extraction.provenance import ExtractedField
from app.extraction.schemas.invoice import Invoice, LineItem
from app.workflows.decision_execute import DecisionExecuteWorkflow
from app.workflows.document_decide import (
    ApplyRails,
    EmitExecute,
    RouteOutcome,
    _seen_before,
)
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
        email=f"gate-{uuid.uuid4().hex[:8]}@example.com",
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


def _invoice(total="850.00", supplier="Contoso Cleaning Services BV", po="PO-2026-0088",
             number=None, due=date(2026, 3, 14)):
    return Invoice(
        supplier=_f(supplier),
        invoice_number=_f(number or f"INV-{uuid.uuid4().hex[:6].upper()}"),
        total_incl_vat=_f(Decimal(total)),
        vat_amount=_f(Decimal("0.00")),
        currency=_f("EUR"),
        issued_on=_f(date(2026, 2, 12)),
        due_on=_f(due) if due else None,
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


def _arm(db, org, **conditions) -> Rule:
    """A rule that really executes. Off by default everywhere else, which is
    why arming it has to be this explicit."""
    rule = Rule(
        org_id=org,
        name="cost centre owner",
        schema_name="invoice",
        conditions={
            "max_total_incl_vat": "1000.00",
            "approved_suppliers": ["Contoso Cleaning Services BV"],
            "require_po": True,
            "min_payment_days": 14,
            **conditions,
        },
        auto_approve=True,
        active=True,
    )
    db.add(rule)
    db.commit()
    return rule


def _staged(db, user, org, invoice: Invoice, proposed=Outcome.auto_approve,
            check_failures=None, unverified=None) -> TaskContext:
    """Everything the rails need, as the earlier nodes would have left it."""
    import json

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
    extraction = Extraction(
        org_id=org,
        document_id=doc.id,
        schema_name="invoice",
        document_text="(parsed invoice)",
        fields=json.loads(invoice.model_dump_json()),
        unverified_fields=unverified or [],
        checks_ok=not check_failures,
        check_failures=check_failures or [],
        model="test",
    )
    db.add(extraction)
    db.commit()

    ctx = TaskContext(
        event_id=uuid.uuid4(),
        event_type="document.decide",
        payload={"document_id": str(doc.id)},
        user_id=str(user.id),
        db=db,
    )
    ctx.metadata.update(
        {
            "document": doc,
            "extracted": invoice,
            "extraction": extraction,
            "unverified": unverified or [],
            "check_failures": check_failures or [],
            "decision_result": DecisionResult(
                decision=ProposedDecision(
                    outcome=proposed,
                    rationale="Under the cost centre limit [1].",
                    unmet_conditions=[],
                ),
                clauses=[],
                grounding_passed=True,
                coverage=None,
            ),
        }
    )
    return ctx


def _through_the_gate(ctx) -> str | None:
    """ApplyRails, then the router. Returns the node it routed to."""
    ApplyRails().process(ctx)
    return RouteOutcome().route(ctx)


# --- the gate fires ------------------------------------------------------


def test_an_armed_rule_carries_a_decision_all_the_way_to_an_execution(db, user, org):
    """The path that had never run. Proposal, rails, router, event, execute."""
    _arm(db, org)
    ctx = _staged(db, user, org, _invoice())

    assert _through_the_gate(ctx) == "EmitExecute"
    EmitExecute().process(ctx)

    decision = ctx.metadata["decision_row"]
    assert decision.outcome == str(Outcome.auto_approve)
    assert decision.rule_id == "cost centre owner"
    assert decision.status is DecisionStatus.approved

    payload = {"decision_id": str(decision.id), "action": "approve_for_payment"}
    DecisionExecuteWorkflow().run(
        TaskContext(
            event_id=uuid.uuid4(),
            event_type="decision.execute",
            payload=payload,
            user_id=str(user.id),
            db=db,
        )
    )

    db.refresh(decision)
    assert decision.status is DecisionStatus.executed
    execution = db.scalar(select(Execution).where(Execution.decision_id == decision.id))
    assert execution.status is ExecutionStatus.succeeded
    assert execution.request["supplier"] == "Contoso Cleaning Services BV"

    # Nobody reviewed it, and that is the whole point: the rule did.
    assert decision.reviewed_by is None
    assert decision.reviewed_at is None


def test_an_automatic_execution_is_still_idempotent(db, user, org):
    """At-least-once delivery must not pay twice, and the automatic path has
    no human double-click to blame if it does."""
    _arm(db, org)
    ctx = _staged(db, user, org, _invoice())
    _through_the_gate(ctx)
    EmitExecute().process(ctx)
    decision = ctx.metadata["decision_row"]

    payload = {"decision_id": str(decision.id), "action": "approve_for_payment"}
    for _ in range(2):
        DecisionExecuteWorkflow().run(
            TaskContext(
                event_id=uuid.uuid4(),
                event_type="decision.execute",
                payload=payload,
                user_id=str(user.id),
                db=db,
            )
        )

    executions = db.scalars(
        select(Execution).where(Execution.decision_id == decision.id)
    ).all()
    assert len(executions) == 1


# --- and refuses to fire ------------------------------------------------


def test_no_rule_means_the_gate_stays_shut(db, user, org):
    """The v1 default, with an invoice that satisfies every condition a rule
    would have imposed. Nothing executes because nothing authorised it."""
    ctx = _staged(db, user, org, _invoice())

    assert _through_the_gate(ctx) == "Done"
    decision = ctx.metadata["decision_row"]
    assert decision.outcome == str(Outcome.route_for_approval)
    assert decision.rule_id is None
    assert decision.status is DecisionStatus.pending_review


def test_an_inactive_rule_authorises_nothing(db, user, org):
    """A rule written but not armed is a note about who approves, not an
    authorisation. `auto_approve=False` is the default for a reason."""
    rule = _arm(db, org)
    rule.auto_approve = False
    db.commit()

    ctx = _staged(db, user, org, _invoice())
    assert _through_the_gate(ctx) == "Done"
    assert ctx.metadata["decision_row"].rule_id is None


@pytest.mark.parametrize(
    ("kwargs", "expected_note"),
    [
        ({"total": "2400.00"}, "over the"),
        ({"po": None}, "no purchase order"),
        ({"supplier": "Blue Yonder Logistics BV"}, "not on the approved list"),
        ({"due": date(2026, 2, 19)}, "shorter than the"),
    ],
    ids=["over the limit", "no purchase order", "unknown supplier", "short payment terms"],
)
def test_each_rule_condition_stops_an_armed_gate(db, user, org, kwargs, expected_note):
    """One condition broken at a time, against a rule that would otherwise
    execute. `min_payment_days` is here because `evals/check_rule.py` found
    short-terms invoices reaching auto_approve with nothing but the model's
    judgement in the way."""
    _arm(db, org)
    ctx = _staged(db, user, org, _invoice(**kwargs))

    assert _through_the_gate(ctx) == "Done"
    decision = ctx.metadata["decision_row"]
    assert decision.outcome == str(Outcome.route_for_approval)
    assert decision.rule_id is None
    assert any(expected_note in note for note in decision.rail_notes), decision.rail_notes


def test_a_failed_check_beats_an_armed_rule(db, user, org):
    """Rail order: the deterministic checks are not a rule condition and no
    rule can waive them. A duplicate arrives here as a check failure."""
    _arm(db, org)
    ctx = _staged(
        db, user, org, _invoice(),
        check_failures=["invoice INV-1 from Contoso was already extracted from another document"],
    )

    assert _through_the_gate(ctx) == "Done"
    decision = ctx.metadata["decision_row"]
    assert decision.outcome == str(Outcome.route_for_approval)
    assert any("already extracted" in note for note in decision.rail_notes)


def test_a_grounding_failure_beats_an_armed_rule(db, user, org):
    """Rail 1 outranks rail 3. A decision nobody can show the policy for does
    not execute because a threshold happened to permit it."""
    _arm(db, org)
    ctx = _staged(db, user, org, _invoice())
    ctx.metadata["decision_result"].grounding_passed = False
    ctx.metadata["decision_result"].grounding_failure = "judge rejected citations [1]"

    assert _through_the_gate(ctx) == "Done"
    assert ctx.metadata["decision_row"].outcome == str(Outcome.needs_human)


# --- the check that closed the last hole ---------------------------------


def test_a_repeated_invoice_number_is_found_by_a_query_not_a_judgement(db, user, org):
    """`evals/check_rule.py` found duplicates were the one deliberate nasty
    reaching auto_approve at every threshold, with nothing but the model's
    memory in the way. A model asked whether it has seen an invoice number
    before is being asked to do a database's job from a context window."""
    invoice = _invoice(number="CON-2026-4041")
    first = _staged(db, user, org, invoice)
    assert _seen_before(db, first.metadata["document"], invoice) == []

    # The same invoice arriving again, as a re-send or a re-scan.
    second = _staged(db, user, org, _invoice(number="CON-2026-4041"))
    failures = _seen_before(db, second.metadata["document"], second.metadata["extracted"])

    assert len(failures) == 1
    assert "CON-2026-4041" in failures[0]
    assert "already extracted" in failures[0]


def test_re_deciding_a_document_does_not_accuse_it_of_duplicating_itself(db, user, org):
    """The match excludes the document, not the extraction: a second run over
    the same file is a re-run, not a duplicate. Getting this backwards would
    make every retry look like fraud."""
    ctx = _staged(db, user, org, _invoice(number="CON-2026-4042"))
    doc = ctx.metadata["document"]

    assert _seen_before(db, doc, ctx.metadata["extracted"]) == []
    # A second extraction of the same document, as a retry would write.
    _staged(db, user, org, _invoice(number="CON-2026-4042"))
    assert _seen_before(db, doc, ctx.metadata["extracted"]) != []


def test_the_same_number_from_a_different_supplier_is_not_a_duplicate(db, user, org):
    """Invoice numbers are only unique within a supplier. Matching on the
    number alone would flag two unrelated companies' first invoice."""
    _staged(db, user, org, _invoice(number="0001", supplier="Contoso Cleaning Services BV"))
    other = _staged(db, user, org, _invoice(number="0001", supplier="Fabrikam Office Supplies BV"))

    assert _seen_before(db, other.metadata["document"], other.metadata["extracted"]) == []


def test_a_duplicate_cannot_be_auto_approved_however_the_rule_is_written(db, user, org):
    """The end of the story `check_rule` started: an armed rule, an invoice
    that meets every one of its conditions, and a number seen before."""
    _arm(db, org)
    _staged(db, user, org, _invoice(number="CON-2026-4043"))

    repeat = _staged(db, user, org, _invoice(number="CON-2026-4043"))
    failures = _seen_before(db, repeat.metadata["document"], repeat.metadata["extracted"])
    repeat.metadata["check_failures"] = failures

    assert _through_the_gate(repeat) == "Done"
    decision = repeat.metadata["decision_row"]
    assert decision.outcome == str(Outcome.route_for_approval)
    assert decision.rule_id is None
