"""FastAPI application entry point.

The OpenAPI schema is the API's contract: it drives the interactive docs
(`/docs`, `/redoc`), and it can generate typed client SDKs. Keep it rich —
every route carries a summary, a response model, and documented error
responses (see the routers and `app/api/schemas.py`).
"""

from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db.engine import engine
from app.logging import configure_logging
from app.observability.request_id import RequestIdMiddleware
from app.observability.sentry import init_sentry

API_DESCRIPTION = """
Backend for the AI-project starter: document upload, an event-driven
ingestion pipeline, and grounded RAG chat with citations.

**Auth** is a httpOnly cookie session (fastapi-users). Call `/auth/register`
then `/auth/jwt/login`; the cookie is sent automatically on subsequent
requests. Interactive docs below can exercise the authenticated routes once
you have logged in.
""".strip()

TAGS_METADATA = [
    {"name": "auth", "description": "Registration, login/logout, password reset, verification."},
    {"name": "users", "description": "The current user (`/users/me`)."},
    {"name": "api-keys", "description": "Create/list/revoke API keys for non-browser clients."},
    {"name": "documents", "description": "Upload (presigned R2), list, delete; ingestion status."},
    {"name": "threads", "description": "Chat threads and their message history."},
    {"name": "chat", "description": "Streaming grounded chat (Server-Sent Events)."},
    {"name": "events", "description": "Generic event intake for background workflows."},
    {"name": "webhooks", "description": "Signed inbound webhooks → events."},
    {"name": "usage", "description": "LLM token usage + cost summary."},
    {"name": "health", "description": "Liveness + readiness probes."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_sentry()
    yield


app = FastAPI(
    title="AI Project API",
    version="0.1.0",
    summary="Document upload, ingestion, and grounded RAG chat.",
    description=API_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    contact={"name": "Stacklane", "url": "https://stacklane.co"},
    license_info={"name": "Proprietary"},
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["authorization", "content-type", "x-api-key", "x-request-id"],
    expose_headers=["x-request-id"],
)


@app.get("/health", tags=["health"], summary="Liveness probe")
def health() -> dict:
    """Cheap liveness check — the process is up. Use `/health/ready` for deps."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"], summary="Readiness probe (DB + Redis)")
def readiness(response: Response) -> dict:
    """Checks the dependencies a request actually needs. Returns 503 if either
    Postgres or Redis is unreachable — point the platform healthcheck here."""
    checks: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
    try:
        redis.from_url(settings.redis_url).ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"

    ok = all(v == "ok" for v in checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ok" if ok else "degraded", "checks": checks}


# Routers are imported late so `app.main` stays importable in isolation
# (tests import individual routers directly).
from app.api.routers import (  # noqa: E402
    api_keys,
    chat,
    decisions,
    documents,
    events,
    threads,
    usage,
    webhooks,
)
from app.auth.backend import auth_backend, fastapi_users  # noqa: E402
from app.auth.schemas import UserCreate, UserRead, UserUpdate  # noqa: E402

# Auth: cookie login/logout, register, password reset, email verification,
# and /users/me. Reset + verify send email via Resend (no-op without a key).
app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"]
)

app.include_router(api_keys.router)
app.include_router(usage.router)
app.include_router(events.router)
app.include_router(webhooks.router)
app.include_router(documents.router)
app.include_router(decisions.router)
app.include_router(threads.router)
app.include_router(chat.router)
