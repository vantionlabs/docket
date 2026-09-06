# Automations: the event engine

Not every project is a chat app. A lot of AI work is **automation**:
webhook- and schedule-driven jobs with no UI. This backend runs those on
the same engine as document ingestion — "workflows execute nodes that pass
data through a TaskContext" — with production reliability built in.

## The lifecycle of an event

```
intake ──> events row (queued) ──> Celery ──> run_event
  · POST /events (authed, Idempotency-Key)         │
  · POST /webhooks/{source} (HMAC-signed)          │
  · internal (e.g. /documents/{id}/confirm)        ▼
                                        workflow_for(type)().run(ctx)
                                          success → done  (+ result)
                                          failure → retry w/ backoff
                                                    └─ exhausted → failed (dead-letter)
```

The `events` row is the durable record and audit trail: `status`,
`attempts`/`max_attempts`, `result`, `error`. Poll `GET /events/{id}`.

## Reliability

**Retries + backoff.** A workflow that raises is retried with exponential
backoff (`EVENT_RETRY_BASE_DELAY_SECONDS · 2^(attempt-1)`, capped) up to the
event's `max_attempts` (`EVENT_MAX_ATTEMPTS`, default 3). Transient failures
(a flaky third-party API) recover on their own.

**Dead-letter.** When attempts are exhausted the event stays as a `failed`
row with the error — never silently dropped. The workflow's `on_failure`
hook runs first, so dependent state is cleaned up (e.g. a document flips out
of `processing`). Inspect dead letters with `GET /events/{id}` or query
`status = 'failed'`.

**Idempotency.** Send an `Idempotency-Key` header to `POST /events`; a
repeated key returns the original event instead of processing twice.
Webhooks dedupe automatically on `X-Webhook-Id` (or a body hash). This makes
at-least-once delivery (every webhook provider, every retried request) safe.

**Crash recovery.** If a worker dies mid-task the event is left in
`processing`. `sweep_stale_events` (Celery beat, every
`STALE_SWEEP_INTERVAL_SECONDS`) requeues events stuck past
`STALE_PROCESSING_MINUTES`, or dead-letters them if retries are exhausted.

## Adding an automation

**1. A workflow** (`app/workflows/your_job.py`):

```python
@register("invoice.reconcile")
class ReconcileWorkflow(Workflow):
    nodes = [FetchInvoices(), MatchPayments(), FlagDiscrepancies()]
```

Import it in `app/workflows/__init__.py` so the worker registers it.

**2a. Trigger by webhook.** A signed `POST /webhooks/{source}` becomes a
`webhook.{source}` event, so register a workflow for `webhook.stripe`,
`webhook.github`, etc. Senders sign the raw body with HMAC-SHA256 and send
`X-Signature-256: sha256=<hex>`; set the shared secret in
`WEBHOOK_SIGNING_SECRET`. (Providers with bespoke schemes — Stripe's
timestamped signatures — need a per-source verifier; branch on `{source}`
in `app/security/webhooks.py`.) See `app/workflows/webhook_example.py`.

**2b. Trigger on a schedule.** Add a task and a beat entry:

```python
# app/worker/tasks.py
@celery_app.task(name="app.nightly_sync")
def nightly_sync() -> None:
    dispatch_event(create_event(db, type="invoice.reconcile", payload={}).id)

# app/worker/celery_app.py — beat_schedule
"nightly-sync": {"task": "app.nightly_sync", "schedule": crontab(hour=2, minute=0)},
```

**2c. Trigger from the API / internally.** `POST /events` with a registered
`type`, or call `app.core.intake.create_event(...)` from your own code (this
is how `/documents/{id}/confirm` emits `document.ingest`).

## What this is not (v1)

No priority queues or multiple queues, no Celery canvas (chords/groups) — a
workflow is one task. No exactly-once across external side effects
(idempotency is at the event boundary; make node side effects idempotent if
they call out). Add these when a project needs them.
