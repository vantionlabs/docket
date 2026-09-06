"""The decide workflow: document in, decision row out (spec sections 5, 6).

Event type `document.decide`, payload `{"document_id": "<uuid>"}`.

This workflow does NOT wait for a human. It ends by writing a `decisions`
row and returning, in seconds. That is the whole trick of section 6: the
event row is already a durable checkpoint with retries, dead-lettering and
crash recovery around it, so cutting the pipeline at the human boundary
gets all of that for free and leaves a pending decision as a database row
anyone can query rather than a suspended coroutine somebody has to trust.

An auto-approved decision emits `decision.execute` from the router. A human
approval emits exactly the same event from the API. One execution path, two
ways to reach it.
"""

import json
import uuid

from app.core.node import Node, RouterNode
from app.core.registry import register
from app.core.task_context import TaskContext
from app.core.workflow import Workflow
from app.db.models import Decision as DecisionRow
from app.db.models import (
    DecisionCitation,
    DecisionStatus,
    Extraction,
    SourceDocument,
)
from app.decisions.decide import decide_invoice
from app.decisions.models import Outcome
from app.decisions.policy import RetrievedPolicy
from app.decisions.rails import apply_rails, rule_for
from app.extraction.arithmetic import check_invoice
from app.extraction.extract import extract
from app.extraction.schemas.invoice import SCHEMA_NAME, Invoice
from app.ingestion.parsing import parse_document
from app.logging import get_logger
from app.storage.r2 import download_bytes

log = get_logger(__name__)


def _document(ctx: TaskContext) -> SourceDocument:
    doc_id = uuid.UUID(str(ctx.payload["document_id"]))
    doc = ctx.db.get(SourceDocument, doc_id)
    if doc is None:
        raise ValueError(f"document {doc_id} not found")
    return doc


class LoadDocument(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        doc = _document(ctx)
        ctx.metadata["document"] = doc
        ctx.nodes[self.name] = {"filename": doc.filename, "collection": str(doc.collection)}
        return ctx


class FetchFromR2(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        doc: SourceDocument = ctx.metadata["document"]
        ctx.metadata["raw"] = download_bytes(doc.r2_key)
        ctx.nodes[self.name] = {"bytes": len(ctx.metadata["raw"])}
        return ctx


class ParseDocument(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        doc: SourceDocument = ctx.metadata["document"]
        text = parse_document(ctx.metadata["raw"], doc.content_type, doc.filename)
        ctx.metadata["text"] = text
        ctx.nodes[self.name] = {"characters": len(text)}
        return ctx


class ExtractFields(Node):
    """Typed extraction, then the two checks that need no model.

    Both results are persisted before anything decides on them, so a
    reviewer can see what was read off the page even when the run later
    fails.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        doc: SourceDocument = ctx.metadata["document"]
        result = extract(ctx.metadata["text"], Invoice, user_id=doc.user_id)
        arithmetic = check_invoice(result.data)

        row = Extraction(
            org_id=doc.org_id,
            document_id=doc.id,
            schema_name=SCHEMA_NAME,
            document_text=ctx.metadata["text"],
            fields=json.loads(result.data.model_dump_json()),
            unverified_fields=result.unverified_fields,
            arithmetic_ok=arithmetic.ok,
            arithmetic_failures=arithmetic.failures,
            model=result.model,
        )
        ctx.db.add(row)
        ctx.db.commit()

        ctx.metadata["invoice"] = result.data
        ctx.metadata["extraction"] = row
        ctx.metadata["unverified"] = result.unverified_fields
        ctx.metadata["arithmetic_failures"] = arithmetic.failures
        ctx.nodes[self.name] = {
            "extraction_id": str(row.id),
            "unverified_fields": result.unverified_fields,
            "arithmetic_ok": arithmetic.ok,
        }
        return ctx


class DecideAgainstPolicy(Node):
    """Retrieve policy, decide, and run both grounding stages.

    Retrieval is confined to `collection=policy`, so the invoice being
    decided cannot be cited as the policy that justifies deciding it.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        doc: SourceDocument = ctx.metadata["document"]
        result = decide_invoice(
            ctx.metadata["invoice"],
            RetrievedPolicy(doc.user_id),
            arithmetic_failures=ctx.metadata["arithmetic_failures"],
            unverified_fields=ctx.metadata["unverified"],
            user_id=doc.user_id,
        )
        ctx.metadata["decision_result"] = result
        ctx.nodes[self.name] = {
            "proposed": str(result.decision.outcome),
            "clauses_retrieved": len(result.clauses),
            "grounding_passed": result.grounding_passed,
            "grounding_failure": result.grounding_failure,
        }
        return ctx


class ApplyRails(Node):
    """The three hard rails, then the decision row (spec section 9).

    The rails run here rather than inside the decision call so that what
    the model proposed and what the system decided are separate facts, both
    recorded. That gap is the override rate, and it is the number that
    tells a client when a threshold can widen.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        doc: SourceDocument = ctx.metadata["document"]
        result = ctx.metadata["decision_result"]
        rule = rule_for(ctx.db, org_id=doc.org_id, schema_name=SCHEMA_NAME)

        final = apply_rails(
            result,
            ctx.metadata["invoice"],
            ctx.metadata["unverified"],
            ctx.metadata["arithmetic_failures"],
            rule=rule,
        )

        row = DecisionRow(
            org_id=doc.org_id,
            user_id=doc.user_id,
            document_id=doc.id,
            extraction_id=ctx.metadata["extraction"].id,
            outcome=str(final.outcome),
            rationale=final.rationale,
            unmet_conditions=final.unmet_conditions,
            rail_notes=final.rail_notes,
            rule_id=final.rule_id,
            grounding_passed=final.grounding_passed,
            grounding_failure=result.grounding_failure or None,
            assigned_to=final.assignee_hint,
            # Everything queues. The router is what changes that, and only
            # for a decision an active rule authorised.
            status=DecisionStatus.pending_review,
        )
        ctx.db.add(row)
        ctx.db.flush()

        for index, clause, excerpt in result.cited:
            ctx.db.add(
                DecisionCitation(
                    decision_id=row.id,
                    chunk_id=clause.chunk_id,
                    document_id=clause.document_id,
                    citation_index=index,
                    clause_ref=clause.ref,
                    excerpt=excerpt,
                )
            )
        ctx.db.commit()

        ctx.metadata["decision_row"] = row
        ctx.metadata["final"] = final
        ctx.nodes[self.name] = {
            "decision_id": str(row.id),
            "outcome": str(final.outcome),
            "rule_id": final.rule_id,
            "citations": len(result.cited),
            "rail_notes": final.rail_notes,
        }
        return ctx


class RouteOutcome(RouterNode):
    """Auto-approve executes; everything else waits in the queue.

    The router is where the workflow ends for a human-bound decision. It
    does not pause anything: it simply stops, and the `decisions` row is
    the checkpoint.
    """

    def route(self, ctx: TaskContext) -> str | None:
        final = ctx.metadata["final"]
        if final.executes_automatically:
            return "EmitExecute"
        log.info(
            "decision.queued",
            decision_id=str(ctx.metadata["decision_row"].id),
            outcome=str(final.outcome),
        )
        return "Done"


class EmitExecute(Node):
    """Emit the same event a human approval emits. One execution path."""

    def process(self, ctx: TaskContext) -> TaskContext:
        from app.decisions.approval import emit_execute

        row = ctx.metadata["decision_row"]
        row.status = DecisionStatus.approved
        ctx.db.commit()
        event = emit_execute(ctx.db, row, action="approve_for_payment")
        ctx.nodes[self.name] = {"event_id": str(event.id), "decision_id": str(row.id)}
        return ctx


class Done(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        row = ctx.metadata["decision_row"]
        ctx.nodes[self.name] = {"decision_id": str(row.id), "status": str(row.status)}
        return ctx


@register("document.decide")
class DocumentDecideWorkflow(Workflow):
    nodes = [
        LoadDocument(),
        FetchFromR2(),
        ParseDocument(),
        ExtractFields(),
        DecideAgainstPolicy(),
        ApplyRails(),
        RouteOutcome(),
        EmitExecute(),
        Done(),
    ]

    def on_failure(self, ctx: TaskContext, exc: Exception) -> None:
        """A run that dies after writing a decision must not leave it
        looking reviewable. Anything else is the event row's business."""
        row = ctx.metadata.get("decision_row")
        if row is None:
            return
        fresh = ctx.db.get(DecisionRow, row.id)
        if fresh is not None and fresh.status is DecisionStatus.pending_review:
            fresh.status = DecisionStatus.failed
            fresh.outcome = str(Outcome.needs_human)
            fresh.rail_notes = [*fresh.rail_notes, f"{type(exc).__name__}: {exc}"[:500]]
            ctx.db.commit()
