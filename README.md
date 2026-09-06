# AI Project — Stacklane client-project boilerplate

A production-shaped starter for custom AI solutions: users upload documents,
an event-driven pipeline chunks and embeds them, and a grounded chat answers
questions **only** from those documents, with verifiable citations. Built to
be copied out per client project and owned by the client.

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12 · FastAPI · uv |
| Workflow engine | Events → Celery (Redis) → Workflow/Node/TaskContext · retries + dead-letter · idempotency · signed webhooks · beat schedules |
| Database | PostgreSQL + pgvector (Railway) · SQLAlchemy 2.0 · Alembic |
| Retrieval | Hybrid: vector (HNSW cosine) + full-text (tsvector) + RRF fusion |
| Agent | PydanticAI · OpenAI / Anthropic (Claude) / Azure via config · structured GroundedAnswer |
| Grounding | Fail-closed validator: registry allowlist + LLM judge |
| Quality | Optional reranking · eval/regression harness (`evals/`) |
| Storage | Cloudflare R2 (presigned browser uploads) |
| Auth | fastapi-users (in the backend) · httpOnly cookie + API keys · UUID users · server-side guard (SSR) |
| Ops | readiness (DB+Redis) · correlation IDs · rate limiting · LLM cost logging · Resend email · optional Sentry |
| Frontend | Next.js (App Router) · Tailwind v4 · shadcn/ui · TanStack Query + Form · Zod · Vercel AI SDK v5 |
| API docs | OpenAPI 3.1 · Swagger UI at `/docs`, ReDoc at `/redoc` · `scripts/export_openapi.py` for SDK gen |
| Streaming | AI-SDK v5 SSE wire format |
| Observability | structlog · optional Langfuse |
| Hosting | Railway (postgres, redis, api, worker, frontend) |

## Quickstart (local)

```bash
# 1. Infra: Postgres (pgvector) + Redis
docker compose up -d postgres redis

# 2. Backend
cd backend
cp .env.example .env            # fill OPENAI_API_KEY + R2_* at minimum
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
# in another terminal:
uv run celery -A app.worker.celery_app worker --loglevel=INFO

# 3. Frontend (thin client — auth lives in the backend)
cd ../frontend
cp .env.example .env            # set NEXT_PUBLIC_API_URL
pnpm install
pnpm dev                        # http://localhost:3000
```

Sign up → upload a document (`.md`/`.txt`; `.pdf` needs
`uv sync --extra docling`) → wait for `ready` → ask a question.

## How it fits together

1. **Auth** lives in this backend (fastapi-users). Login sets an httpOnly
   cookie holding a JWT the backend verifies locally — the token is never
   exposed to JavaScript (XSS-safe), and `SameSite=Lax` blocks CSRF. The
   `get_current_user` seam swaps cleanly to enterprise SSO/OIDC per project
   (see docs/setup-auth.md).
2. **Uploads** never touch the API: the browser PUTs straight to R2 with a
   presigned URL, then confirms. Confirmation emits a `document.ingest`
   **event**; a Celery worker runs the registered workflow
   (fetch → parse → chunk → embed → store) and flips the document status.
3. **Chat** is synchronous SSE (streaming UX ≠ queue work): hybrid retrieval
   feeds a PydanticAI agent whose tools record every retrieved chunk into a
   per-turn registry; a fail-closed validator checks each citation
   structurally and with an LLM judge before anything is streamed or saved.
4. **Automations** run on the same engine — signed webhooks and Celery beat
   schedules feed events, processed with retries, dead-lettering,
   idempotency, and crash recovery. See `docs/automations.md`.

Read `docs/architecture.md` for the full request flows, and `AGENTS.md`
for the conventions AI coding agents must follow in this repo.

## Deploy

Railway, five services: Postgres (pgvector), Redis, api + worker (same
image, different start commands), frontend. Step-by-step:
`docs/setup-railway.md`, `docs/setup-r2.md`, `docs/setup-auth.md`.
