# Operations

The production layer: health, tracing, rate limits, cost visibility, API
keys, and email. Everything optional is env-gated and no-ops when unset, so
the template runs locally with nothing configured.

## Health checks

- `GET /health` — cheap liveness (the process is up).
- `GET /health/ready` — readiness: checks Postgres **and** Redis, returns
  **503** if either is down. Point the platform healthcheck (Railway) here so
  a broken dependency stops traffic. Body: `{"status", "checks": {...}}`.

## Correlation IDs

Every request gets an `X-Request-ID` (from the inbound header or generated),
bound to structlog so every log line for that request — API, SQL, LLM,
workflow — carries the same id, and echoed back in the response header. Quote
it in a bug report to pull the whole trace.

## Error tracking (Sentry)

Set `SENTRY_DSN` and install the extra (`uv sync --extra sentry`). Captures
unhandled exceptions in the API and worker. `send_default_pii=False` — no
request bodies or user data leave your infra by default. No DSN → no-op.

## Rate limiting

`app/security/ratelimit.py` is a Redis fixed-window limiter applied to
`/chat/stream` (the costly path): `CHAT_RATE_LIMIT` requests per
`CHAT_RATE_WINDOW_SECONDS` per user, `429` when exceeded (with `Retry-After`).
It **fails open** if Redis blips (a limiter outage shouldn't take down the
API). To protect another route, add `Depends(RateLimiter(limit, window,
"scope"))`.

## API keys (non-browser clients)

For service-to-service, headless, and widget clients that can't use the
cookie session. Create one while logged in:

```
POST /api-keys {"name": "..."}   → { key: "sk_...", ... }   # plaintext shown ONCE
GET  /api-keys                    → list (no secrets)
DELETE /api-keys/{id}             → revoke
```

Then call the app routes with `X-API-Key: sk_...` instead of the cookie —
both resolve through the same `get_current_user` seam. We store only the
SHA-256 hash of the key. (Note: the fastapi-users `/users/me` route is
cookie-only; API-key clients use the app routes.)

## LLM usage + cost

Every model call (chat, embedding, grounding) writes an `llm_usage` row with
token counts and a computed cost. Prices live in
`app/observability/usage.py` (`PRICES`, USD per 1M tokens) — **update them
when rates change or you add a model**; unknown models log at cost 0.

```
GET /usage?days=30   → { total_cost_usd, by_operation: [...] }
```

Use it for a client-facing spend view, or as the basis for per-user quotas
(query the table in a rate-limit-style dependency).

## Email (Resend)

`app/email/client.py` sends via Resend's REST API. Set `RESEND_API_KEY` +
`EMAIL_FROM`; without a key, sends are logged and skipped (safe for
dev/tests). Password reset (`POST /auth/forgot-password`) and verification
(`POST /auth/request-verify-token`) are wired to it — the links point at
`FRONTEND_URL`, so add `/reset-password` and `/verify-email` pages to the
frontend to complete those flows. `send_email(...)` is also available for
notification workflows.
