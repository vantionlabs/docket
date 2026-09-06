"""Document ingestion workflow (the Launchpad pattern, applied).

Event type `document.ingest`, payload `{"document_id": "<uuid>"}`.
Nodes: FetchFromR2 -> ParseDocument -> ChunkDocument -> EmbedChunks -> StoreChunks.
The workflow flips the document's status: processing -> ready/failed
(failure is recorded by the worker via the event row; the LoadDocument
node also mirrors it onto the document so the frontend sees it).
"""

import uuid

from app.core.node import Node
from app.core.registry import register
from app.core.task_context import TaskContext
from app.core.workflow import Workflow
from app.db.models import DocumentChunk, DocumentStatus, SourceDocument
from app.ingestion.chunking import chunk_text
from app.ingestion.parsing import parse_document
from app.retrieval.embeddings import embed_batch
from app.storage.r2 import download_bytes


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
    def process(self, ctx: TaskContext) -> TaskContext:
        chunks = ctx.metadata["chunks"]
        ctx.metadata["vectors"] = embed_batch([c.content for c in chunks])
        ctx.nodes[self.name] = {"embedded": len(chunks)}
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


@register("document.ingest")
class DocumentIngestWorkflow(Workflow):
    nodes = [
        MarkProcessing(),
        FetchFromR2(),
        ParseDocument(),
        ChunkDocument(),
        EmbedChunks(),
        StoreChunks(),
    ]

    def on_failure(self, ctx: TaskContext, exc: Exception) -> None:
        """Mirror the failure onto the document so it never wedges in
        `processing` and the frontend can show the error."""
        doc = _document(ctx)
        doc.status = DocumentStatus.failed
        doc.error = f"{type(exc).__name__}: {exc}"[:500]
        ctx.db.commit()
