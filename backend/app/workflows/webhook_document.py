"""Signed-webhook intake: an external system hands us a document.

Event type `webhook.document`, from `POST /webhooks/document`. Payload:

    {
      "external_ref": "supplier-portal-88213",   # required, the dedupe key
      "filename": "invoice.pdf",
      "content_type": "application/pdf",
      "collection": "transactional",             # or "policy"
      "content_base64": "...",                   # the document itself
      "owner_email": "ap@northwind.nl"           # whose org it belongs to
    }

**Content is inline, never a URL, on purpose.** Fetching a URL out of an
inbound payload would give anyone who can post a signed webhook an outbound
HTTP request from inside the network, aimed wherever they like. The
signature proves the sender holds the shared secret; it does not make the
URL inside safe, and a leaked secret should not also be an SSRF primitive.
Senders that only have a URL should fetch it themselves and post the bytes.

The webhook is unauthenticated in the session sense (trust comes from the
HMAC), so the payload names the owner and the workflow resolves it to a
real user and org. An unknown owner is rejected rather than guessed.
"""

import base64
import binascii

from sqlalchemy import select

from app.core.document_intake import document_from_payload, receive_document
from app.core.node import Node
from app.core.registry import register
from app.core.task_context import TaskContext
from app.core.workflow import Workflow
from app.db.models import User
from app.logging import get_logger
from app.storage.r2 import object_key, upload_bytes

log = get_logger(__name__)

# A cap so a webhook cannot post something enormous into storage. Real
# invoices are kilobytes; a scanned multi-page PDF is a few megabytes.
MAX_BYTES = 25 * 1024 * 1024


class ResolveOwner(Node):
    """Whose org does this document belong to?

    Rejects rather than guesses. A document filed against the wrong tenant
    is worse than a document that failed to arrive, because the second gets
    noticed.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        email = str(ctx.payload.get("owner_email") or "").strip().lower()
        if not email:
            raise ValueError("webhook payload has no owner_email")

        user = ctx.db.scalar(select(User).where(User.email == email))
        if user is None:
            raise ValueError(f"no user for owner_email {email!r}")

        from app.auth.orgs import active_membership

        membership = active_membership(ctx.db, user.id, user.email)
        ctx.metadata["user"] = user
        ctx.metadata["org_id"] = membership.org_id
        ctx.nodes[self.name] = {"user_id": str(user.id), "org_id": str(membership.org_id)}
        return ctx


class DecodeContent(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        encoded = ctx.payload.get("content_base64")
        if not encoded:
            raise ValueError("webhook payload has no content_base64")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("content_base64 is not valid base64") from exc
        if not raw:
            raise ValueError("content_base64 decoded to nothing")
        if len(raw) > MAX_BYTES:
            raise ValueError(f"document is {len(raw)} bytes, over the {MAX_BYTES} limit")

        ctx.metadata["raw"] = raw
        ctx.nodes[self.name] = {"bytes": len(raw)}
        return ctx


class StoreAndQueue(Node):
    """Put the bytes in storage, record the intake, queue the pipeline."""

    def process(self, ctx: TaskContext) -> TaskContext:
        user = ctx.metadata["user"]
        raw = ctx.metadata["raw"]
        external_ref = str(ctx.payload.get("external_ref") or "") or None

        content_type = str(ctx.payload.get("content_type") or "application/octet-stream")
        key = object_key(str(user.id), str(ctx.payload.get("filename") or "document"))
        upload_bytes(key, raw, content_type)

        document = document_from_payload(
            ctx.db,
            ctx.payload,
            user_id=user.id,
            org_id=ctx.metadata["org_id"],
            r2_key=key,
        )
        document.size_bytes = len(raw)

        event, created = receive_document(
            ctx.db,
            document,
            source="webhook",
            external_ref=external_ref,
            raw={k: v for k, v in ctx.payload.items() if k != "content_base64"},
        )
        ctx.nodes[self.name] = {
            "document_id": str(document.id),
            "event_id": str(event.id) if event else None,
            "queued": created,
        }
        return ctx


@register("webhook.document")
class WebhookDocumentWorkflow(Workflow):
    nodes = [ResolveOwner(), DecodeContent(), StoreAndQueue()]
