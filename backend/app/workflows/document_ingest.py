"""Document ingestion workflow (the Launchpad pattern, applied).

Event type `document.ingest`, payload `{"document_id": "<uuid>"}`.
Nodes: FetchFromR2 -> ParseDocument -> ChunkDocument -> EmbedChunks -> StoreChunks.
The workflow flips the document's status: processing -> ready/failed
(failure is recorded by the worker via the event row; the LoadDocument
node also mirrors it onto the document so the frontend sees it).
"""

import uuid

from sqlalchemy import select

from app.config import settings
from app.core.node import Node
from app.core.registry import register
from app.core.task_context import TaskContext
from app.core.workflow import Workflow
from app.db.models import (
    Collection,
    DocumentChunk,
    DocumentStatus,
    PolicyObligation,
    SourceDocument,
)
from app.ingestion.chunking import chunk_text
from app.ingestion.context import contextualize
from app.ingestion.parsing import parse_document
from app.logging import get_logger
from app.retrieval.embeddings import embed_documents
from app.storage.r2 import download_bytes

log = get_logger(__name__)


def _document(ctx: TaskContext) -> SourceDocument:
    doc_id = uuid.UUID(str(ctx.payload["document_id"]))
    doc = ctx.db.get(SourceDocument, doc_id)
    if doc is None:
        raise ValueError(f"document {doc_id} not found")
    return doc


class MarkProcessing(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        doc = _document(ctx)
        doc.status = DocumentStatus.processing
        doc.error = None
        ctx.db.commit()
        ctx.metadata["document"] = doc
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


class ChunkDocument(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        chunks = chunk_text(ctx.metadata["text"])
        ctx.metadata["chunks"] = chunks
        ctx.nodes[self.name] = {"chunks": len(chunks)}
        return ctx


class EmbedChunks(Node):
    """Embed each chunk, with the context chunking took away.

    A chunk that reads "This does not apply to intercompany recharges" is
    about nothing once it is separated from the heading above it, and will
    not be retrieved for a question about what the rule covers. So the text
    that gets embedded carries the document name and heading path
    (app/ingestion/context.py); the text that gets STORED does not, because
    a citation quotes the document rather than our note about it.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        doc: SourceDocument = ctx.metadata["document"]
        chunks = ctx.metadata["chunks"]
        document_text = ctx.metadata["text"]

        embed_texts = [
            contextualize(chunk.content, doc.filename, document_text=document_text)
            for chunk in chunks
        ]
        # Documents, not queries: the provider embeds the two differently.
        ctx.metadata["vectors"] = embed_documents(embed_texts)
        ctx.nodes[self.name] = {
            "embedded": len(chunks),
            "contextual_retrieval": settings.contextual_retrieval,
        }
        return ctx


class StoreChunks(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        doc: SourceDocument = ctx.metadata["document"]
        chunks = ctx.metadata["chunks"]
        vectors = ctx.metadata["vectors"]

        # Idempotent re-ingest: replace any existing chunks for this document.
        ctx.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()
        ctx.db.add_all(
            DocumentChunk(
                document_id=doc.id,
                user_id=doc.user_id,
                org_id=doc.org_id,
                # Chunks inherit the document's collection, so the retrieval
                # filter can never disagree with the document it came from.
                collection=doc.collection,
                chunk_index=chunk.index,
                content=chunk.content,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        )
        doc.status = DocumentStatus.ready
        ctx.db.commit()
        ctx.nodes[self.name] = {"stored": len(chunks), "status": "ready"}
        return ctx


class IndexObligations(Node):
    """Index a policy document into the obligations its clauses impose.

    Runs only for the policy collection, and only after the chunks exist,
    because an obligation points at the chunk that states it. For anything
    transactional this is a no-op: an invoice imposes no rules.

    This is what makes coverage checking possible later (see
    app/decisions/coverage.py). It costs one cheap model call per chunk,
    once, at ingest, rather than anything at decision time.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        doc: SourceDocument = ctx.metadata["document"]
        if doc.collection is not Collection.policy:
            ctx.nodes[self.name] = {"skipped": "not a policy document"}
            return ctx

        from app.decisions.coverage import extract_obligations
        from app.decisions.policy import _clause_ref

        # Re-indexing replaces: a policy that changed should not leave the
        # rules it used to impose lying around as coverage requirements.
        ctx.db.query(PolicyObligation).filter(
            PolicyObligation.document_id == doc.id
        ).delete()
        ctx.db.commit()

        stored = 0
        for chunk in ctx.db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
        ):
            ref = _clause_ref(doc.filename, chunk.content, chunk.chunk_index)
            for obligation in extract_obligations(
                chunk.content, ref, document_title=doc.filename
            ):
                ctx.db.add(
                    PolicyObligation(
                        org_id=doc.org_id,
                        document_id=doc.id,
                        chunk_id=chunk.id,
                        dimension=obligation["dimension"],
                        summary=obligation["summary"],
                        clause_ref=ref,
                        schema_name=obligation.get("governs", "invoice"),
                        in_force=obligation.get("in_force", True),
                        always_applies=obligation.get("always_applies", False),
                        threshold=obligation.get("threshold"),
                    )
                )
                stored += 1
        ctx.db.commit()

        log.info("policy.indexed", document_id=str(doc.id), obligations=stored)
        ctx.nodes[self.name] = {"obligations": stored}
        return ctx


@register("document.ingest")
class DocumentIngestWorkflow(Workflow):
    nodes = [
        MarkProcessing(),
        FetchFromR2(),
        ParseDocument(),
        ChunkDocument(),
        EmbedChunks(),
        StoreChunks(),
        IndexObligations(),
    ]

    def on_failure(self, ctx: TaskContext, exc: Exception) -> None:
        """Mirror the failure onto the document so it never wedges in
        `processing` and the frontend can show the error."""
        doc = _document(ctx)
        doc.status = DocumentStatus.failed
        doc.error = f"{type(exc).__name__}: {exc}"[:500]
        ctx.db.commit()
