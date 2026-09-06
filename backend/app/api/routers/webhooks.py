"""Signed webhook ingress → the event engine.

External systems POST here; a verified webhook becomes an event of type
`webhook.{source}`, processed by the workflow registered for that type.
Unauthenticated by design — trust comes from the HMAC signature, not a user
session — so `user_id` is null on these events.

Register a workflow per source you accept:

    @register("webhook.stripe")
    class StripeWebhookWorkflow(Workflow): ...
"""

import hashlib
import json

from fastapi import APIRouter, HTTPException, Request

from app.core.intake import create_event
from app.core.registry import registered_types
from app.db.engine import SessionLocal
from app.security.webhooks import verify_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/{source}",
    status_code=202,
    summary="Receive a signed webhook",
    description=(
        "Verifies the HMAC signature, then turns the payload into a "
        "`webhook.{source}` event. Idempotent per `X-Webhook-Id` (falls back "
        "to a hash of the body). Returns `{event_id}`."
    ),
    responses={
        401: {"description": "Missing or invalid signature"},
        404: {"description": "No workflow registered for this source"},
    },
)
async def receive_webhook(source: str, request: Request) -> dict:
    raw = await request.body()
    signature = request.headers.get(_signature_header())
    if not verify_signature(raw, signature):
        raise HTTPException(401, "Invalid signature")

    event_type = f"webhook.{source}"
    if event_type not in registered_types():
        raise HTTPException(404, f"No workflow registered for {event_type!r}")

    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Body is not valid JSON") from exc

    # Idempotency: providers send a delivery id; fall back to a body hash.
    delivery_id = request.headers.get("X-Webhook-Id") or hashlib.sha256(raw).hexdigest()
    idempotency_key = f"{event_type}:{delivery_id}"

    with SessionLocal() as db:
        event, _created = create_event(
            db, type=event_type, payload=payload, idempotency_key=idempotency_key
        )
        return {"event_id": str(event.id)}


def _signature_header() -> str:
    from app.config import settings

    return settings.webhook_signature_header
