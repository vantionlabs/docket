"""The execute workflow: an approved decision becomes a side effect.

Event type `decision.execute`, payload
`{"decision_id": "<uuid>", "action": "approve_for_payment"}`.

Events retry. Side effects that call a payment or accounting system must
therefore be idempotent or somebody gets paid twice, and the guarantee
lives in the database rather than in this file: the `executions` row is
written with a unique key BEFORE the outbound call, and a retry that finds
a completed row returns it and calls nothing (spec section 10).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.adapters import AdapterRequest, get_adapter
from app.core.node import Node
from app.core.registry import register
from app.core.task_context import TaskContext
from app.core.workflow import Workflow
from app.db.models import Decision as DecisionRow
from app.db.models import DecisionStatus, Execution, ExecutionStatus, Extraction
from app.decisions.approval import execution_key
from app.logging import get_logger

log = get_logger(__name__)


def _decision(ctx: TaskContext) -> DecisionRow:
    decision_id = uuid.UUID(str(ctx.payload["decision_id"]))
    row = ctx.db.get(DecisionRow, decision_id)
    if row is None:
        raise ValueError(f"decision {decision_id} not found")
    return row


class CheckIdempotency(Node):
    """Claim the work, or find it already done.

    Inserting the row is the claim. The unique constraint on
    `idempotency_key` means two concurrent retries cannot both succeed
    here, so exactly one of them goes on to call the adapter.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        decision = _decision(ctx)
        action = str(ctx.payload.get("action", "approve_for_payment"))
        key = execution_key(decision.id, action)
        adapter = get_adapter()

        existing = ctx.db.scalar(select(Execution).where(Execution.idempotency_key == key))
        if existing is not None and existing.status is ExecutionStatus.succeeded:
            ctx.metadata["already_done"] = True
            ctx.metadata["execution"] = existing
            ctx.nodes[self.name] = {
                "execution_id": str(existing.id),
                "replayed": True,
                "external_reference": (existing.response or {}).get("external_reference"),
            }
            log.info("execution.replayed", decision_id=str(decision.id), key=key)
            return ctx

        if existing is None:
            existing = Execution(
                org_id=decision.org_id,
                decision_id=decision.id,
                adapter=adapter.name,
                idempotency_key=key,
                status=ExecutionStatus.pending,
            )
            ctx.db.add(existing)
            try:
                ctx.db.commit()
            except IntegrityError:
                # A concurrent attempt claimed it first. Let that one finish.
                ctx.db.rollback()
                existing = ctx.db.scalar(
                    select(Execution).where(Execution.idempotency_key == key)
                )
                if existing is None:
                    raise
                ctx.metadata["already_done"] = True
                ctx.metadata["execution"] = existing
                ctx.nodes[self.name] = {"execution_id": str(existing.id), "conceded": True}
                return ctx

        ctx.metadata["already_done"] = False
        ctx.metadata["decision"] = decision
        ctx.metadata["execution"] = existing
        ctx.metadata["action"] = action
        ctx.nodes[self.name] = {"execution_id": str(existing.id), "adapter": adapter.name}
        return ctx


class CallAdapter(Node):
    """The one outbound call, and the only place Docket changes the world."""

    def process(self, ctx: TaskContext) -> TaskContext:
        if ctx.metadata.get("already_done"):
            ctx.nodes[self.name] = {"skipped": "already executed"}
            return ctx

        decision: DecisionRow = ctx.metadata["decision"]
        execution: Execution = ctx.metadata["execution"]
        adapter = get_adapter()

        request = _build_request(ctx, decision)
        execution.request = request.to_json()
        ctx.db.commit()

        try:
            response = adapter.execute(request)
        except Exception as exc:
            execution.status = ExecutionStatus.failed
            execution.error = f"{type(exc).__name__}: {exc}"[:1000]
            execution.completed_at = datetime.now(UTC)
            ctx.db.commit()
            raise

        ctx.metadata["response"] = response
        ctx.nodes[self.name] = {"ok": response.ok, "adapter": adapter.name}
        return ctx


def _build_request(ctx: TaskContext, decision: DecisionRow) -> AdapterRequest:
    """What the adapter is told, read back from the extraction row.

    Read back rather than passed through, because the execute workflow runs
    from an event that may be minutes or days after the decide workflow.
    The extraction row is the record of what was on the page.
    """
    fields: dict = {}
    if decision.extraction_id is not None:
        extraction = ctx.db.get(Extraction, decision.extraction_id)
        if extraction is not None:
            fields = extraction.fields or {}

    def value(name: str, default: str = "") -> str:
        field = fields.get(name)
        if isinstance(field, dict) and "value" in field:
            return str(field["value"])
        return default

    return AdapterRequest(
        decision_id=decision.id,
        action=str(ctx.metadata["action"]),
        supplier=value("supplier", "unknown supplier"),
        reference=value("invoice_number", str(decision.document_id)),
        amount=value("total_incl_vat", "0"),
        currency=value("currency", "EUR"),
        assignee_hint=decision.assigned_to,
        note=decision.override_note or decision.rationale,
    )


class RecordExecution(Node):
    """Close the loop: the response, and the decision's final status."""

    def process(self, ctx: TaskContext) -> TaskContext:
        if ctx.metadata.get("already_done"):
            ctx.nodes[self.name] = {"skipped": "already executed"}
            return ctx

        decision: DecisionRow = ctx.metadata["decision"]
        execution: Execution = ctx.metadata["execution"]
        response = ctx.metadata["response"]

        execution.response = response.to_json()
        execution.status = (
            ExecutionStatus.succeeded if response.ok else ExecutionStatus.failed
        )
        execution.completed_at = datetime.now(UTC)
        if not response.ok:
            execution.error = "adapter reported failure"

        decision.status = (
            DecisionStatus.executed if response.ok else DecisionStatus.failed
        )
        ctx.db.commit()

        ctx.nodes[self.name] = {
            "execution_id": str(execution.id),
            "status": str(execution.status),
            "external_reference": response.external_reference,
            "decision_status": str(decision.status),
        }
        return ctx


class NotifySubmitter(Node):
    """Tell whoever is waiting. Never fails the workflow.

    A notification that does not arrive is a bad day. A notification that
    fails the workflow re-runs the side effect, and that is a much worse
    one, so this node swallows its own errors on purpose.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        if ctx.metadata.get("already_done"):
            ctx.nodes[self.name] = {"skipped": "already executed"}
            return ctx

        decision: DecisionRow = ctx.metadata["decision"]
        try:
            log.info(
                "decision.executed",
                decision_id=str(decision.id),
                outcome=decision.effective_outcome,
                status=str(decision.status),
            )
            ctx.nodes[self.name] = {"notified": True}
        except Exception:  # noqa: BLE001 -- never re-run a side effect over a notice
            log.exception("notify.failed", decision_id=str(decision.id))
            ctx.nodes[self.name] = {"notified": False}
        return ctx


@register("decision.execute")
class DecisionExecuteWorkflow(Workflow):
    nodes = [
        CheckIdempotency(),
        CallAdapter(),
        RecordExecution(),
        NotifySubmitter(),
    ]

    def on_failure(self, ctx: TaskContext, exc: Exception) -> None:
        """Mark the decision failed so it never looks executed.

        The execution row keeps `pending` when the adapter never ran, which
        is what lets a retry claim it again; only a completed call closes it.
        """
        decision = ctx.metadata.get("decision")
        if decision is None:
            return
        fresh = ctx.db.get(DecisionRow, decision.id)
        if fresh is not None and fresh.status is not DecisionStatus.executed:
            fresh.status = DecisionStatus.failed
            ctx.db.commit()
