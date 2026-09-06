"""M2: the two workflows, the split at the human boundary, idempotency.

Offline. Nodes are exercised against fakes rather than a database, because
what these tests are checking is control flow: does the router send an
auto-approved decision to execute and a queued one to the end, does a
replayed execution call the adapter a second time, does one execution path
serve both approvals.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.adapters import AdapterRequest, DryRunAdapter, get_adapter
from app.core.task_context import TaskContext
from app.core.workflow import Workflow
from app.db.models import DecisionStatus, ExecutionStatus
from app.decisions.approval import execution_key
from app.decisions.models import Outcome
from app.decisions.rails import AutoApproveRule, from_row
from app.extraction.provenance import ExtractedField
from app.extraction.schemas.invoice import Invoice
from app.workflows.decision_execute import (
    CallAdapter,
    CheckIdempotency,
    RecordExecution,
)
from app.workflows.document_decide import RouteOutcome


def _field(value):
    return ExtractedField(value=value, source_span=str(value))


def _invoice(total="859.10"):
    return Invoice(
        supplier=_field("Contoso Cleaning Services BV"),
        invoice_number=_field("CCS-2026-0411"),
        total_incl_vat=_field(Decimal(total)),
        vat_amount=_field(Decimal("149.10")),
        currency=_field("EUR"),
        issued_on=_field("2026-02-12"),
        po_number=_field("PO-2026-0088"),
    )


@dataclass
class _Final:
    """Stands in for rails.FinalDecision, which the router only reads one
    property from."""

    outcome: Outcome

    @property
    def executes_automatically(self) -> bool:
        return self.outcome is Outcome.auto_approve


def _ctx(**metadata) -> TaskContext:
    return TaskContext(
        event_id=uuid.uuid4(),
        event_type="test.event",
        payload={},
        user_id=str(uuid.uuid4()),
        db=MagicMock(),
        metadata=dict(metadata),
    )


# --- the split at the human boundary (spec section 6) -------------------


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (Outcome.auto_approve, "EmitExecute"),
        (Outcome.route_for_approval, "Done"),
        (Outcome.reject, "Done"),
        (Outcome.needs_human, "Done"),
    ],
)
def test_router_only_executes_an_auto_approval(outcome, expected):
    ctx = _ctx(final=_Final(outcome), decision_row=MagicMock(id=uuid.uuid4()))
    assert RouteOutcome().route(ctx) == expected


def test_router_targets_are_real_nodes():
    """A router that names a node the workflow does not have raises at run
    time, deep inside a Celery task. Catch it here instead."""
    from app.workflows.document_decide import DocumentDecideWorkflow

    names = {node.name for node in DocumentDecideWorkflow.nodes}
    assert {"EmitExecute", "Done"} <= names


def test_decide_workflow_never_waits():
    """The decide workflow must end. Nothing in it may block on a human:
    that is the whole design (spec section 6)."""
    from app.workflows.document_decide import DocumentDecideWorkflow

    names = [node.name for node in DocumentDecideWorkflow.nodes]
    assert names[-1] == "Done"
    assert "Wait" not in " ".join(names)


# --- one execution path -------------------------------------------------


def test_both_approval_paths_use_the_same_idempotency_key():
    """The router's auto-approve and a reviewer's approve must collide on
    purpose, so a decision cannot execute twice by arriving twice."""
    decision_id = uuid.uuid4()
    assert execution_key(decision_id, "approve_for_payment") == execution_key(
        decision_id, "approve_for_payment"
    )
    assert execution_key(decision_id, "approve_for_payment") != execution_key(
        decision_id, "reject"
    )
    assert str(decision_id) in execution_key(decision_id, "approve_for_payment")


# --- idempotent execution (spec section 10) -----------------------------


@dataclass
class _FakeExecution:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: ExecutionStatus = ExecutionStatus.pending
    response: dict | None = None
    request: dict | None = None
    error: str | None = None
    completed_at: object = None


class _CountingAdapter:
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: AdapterRequest):
        from app.adapters.base import AdapterResponse

        self.calls += 1
        return AdapterResponse(ok=True, external_reference=f"ref-{self.calls}")


def test_a_completed_execution_is_never_called_again(monkeypatch):
    """The core of section 10: a retry that finds a succeeded row does
    nothing. This is what stops a supplier being paid twice."""
    adapter = _CountingAdapter()
    monkeypatch.setattr("app.workflows.decision_execute.get_adapter", lambda *a, **k: adapter)

    done = _FakeExecution(
        status=ExecutionStatus.succeeded, response={"external_reference": "ref-original"}
    )
    db = MagicMock()
    db.get.return_value = MagicMock(id=uuid.uuid4(), org_id=None, extraction_id=None)
    db.scalar.return_value = done

    ctx = _ctx()
    ctx.payload = {"decision_id": str(uuid.uuid4()), "action": "approve_for_payment"}
    ctx.db = db

    ctx = CheckIdempotency().process(ctx)
    assert ctx.metadata["already_done"] is True

    ctx = CallAdapter().process(ctx)
    ctx = RecordExecution().process(ctx)
    assert adapter.calls == 0
    assert ctx.nodes["CallAdapter"] == {"skipped": "already executed"}


def test_a_fresh_execution_calls_the_adapter_once(monkeypatch):
    adapter = _CountingAdapter()
    monkeypatch.setattr("app.workflows.decision_execute.get_adapter", lambda *a, **k: adapter)

    decision = MagicMock(
        id=uuid.uuid4(),
        org_id=None,
        extraction_id=None,
        document_id=uuid.uuid4(),
        assigned_to="FAC-01",
        override_note=None,
        rationale="Under the limit [1].",
        status=DecisionStatus.approved,
    )
    db = MagicMock()
    db.get.return_value = decision
    db.scalar.return_value = None  # nothing claimed yet

    ctx = _ctx()
    ctx.payload = {"decision_id": str(decision.id), "action": "approve_for_payment"}
    ctx.db = db

    ctx = CheckIdempotency().process(ctx)
    assert ctx.metadata["already_done"] is False

    ctx = CallAdapter().process(ctx)
    assert adapter.calls == 1
    assert ctx.metadata["response"].ok


def test_execution_row_is_written_before_the_call(monkeypatch):
    """Order matters: a row written after the call cannot protect it."""
    calls: list[str] = []

    class _Recording:
        name = "recording"

        def execute(self, request):
            from app.adapters.base import AdapterResponse

            calls.append("adapter")
            return AdapterResponse(ok=True, external_reference="ref")

    monkeypatch.setattr(
        "app.workflows.decision_execute.get_adapter", lambda *a, **k: _Recording()
    )

    db = MagicMock()
    db.get.return_value = MagicMock(
        id=uuid.uuid4(), org_id=None, extraction_id=None, document_id=uuid.uuid4(),
        assigned_to=None, override_note=None, rationale="",
    )
    db.scalar.return_value = None
    db.add.side_effect = lambda *a, **k: calls.append("db.add")

    ctx = _ctx()
    ctx.payload = {"decision_id": str(uuid.uuid4()), "action": "approve_for_payment"}
    ctx.db = db

    ctx = CheckIdempotency().process(ctx)
    ctx = CallAdapter().process(ctx)
    assert calls == ["db.add", "adapter"]


# --- the adapter surface ------------------------------------------------


def test_dry_run_is_the_default():
    """An unconfigured deployment must do nothing, not guess."""
    assert get_adapter().name == "dry_run"


def test_unknown_adapter_falls_back_to_dry_run():
    assert get_adapter("no-such-adapter").name == "dry_run"


def test_dry_run_changes_nothing_and_says_so():
    response = DryRunAdapter().execute(
        AdapterRequest(
            decision_id=uuid.uuid4(),
            action="approve_for_payment",
            supplier="Contoso Cleaning Services BV",
            reference="CCS-2026-0411",
            amount="859.10",
            currency="EUR",
        )
    )
    assert response.ok
    assert "dry-run" in response.external_reference
    assert "Nothing was paid" in response.detail["note"]


# --- rules loaded from the database -------------------------------------


def test_a_half_configured_rule_approves_nothing():
    """A missing threshold means zero, not infinity."""
    row = MagicMock(name_="r", conditions={}, active=True, auto_approve=True)
    row.name = "half-configured"
    rule = from_row(row)
    assert rule.max_total_incl_vat == Decimal("0")
    assert rule.unmet(_invoice())


def test_auto_approve_false_makes_the_rule_inactive():
    """`active` on the row is not enough. Rail 3 needs auto_approve too."""
    row = MagicMock(conditions={"max_total_incl_vat": "10000"}, active=True, auto_approve=False)
    row.name = "not-armed"
    assert from_row(row).active is False


def test_a_fully_configured_rule_permits_its_own_invoice():
    row = MagicMock(
        conditions={
            "max_total_incl_vat": "1000",
            "approved_suppliers": ["Contoso Cleaning Services BV"],
            "require_po": True,
        },
        active=True,
        auto_approve=True,
    )
    row.name = "cost-centre-owner-limit"
    rule = from_row(row)
    assert isinstance(rule, AutoApproveRule)
    assert rule.active
    assert rule.unmet(_invoice()) == []


# --- the workflow engine holds the shape we rely on ---------------------


def test_router_jump_skips_the_execute_node():
    """Proves the engine really skips forward, rather than the test only
    proving what `route` returns."""

    class _Recorder(Workflow):
        pass

    visited: list[str] = []

    from app.core.node import Node, RouterNode

    class A(Node):
        def process(self, ctx):
            visited.append("A")
            return ctx

    class R(RouterNode):
        def route(self, ctx):
            return "C"

    class B(Node):
        def process(self, ctx):
            visited.append("B")
            return ctx

    class C(Node):
        def process(self, ctx):
            visited.append("C")
            return ctx

    _Recorder.nodes = [A(), R(), B(), C()]
    _Recorder().run(_ctx())
    assert visited == ["A", "C"]
