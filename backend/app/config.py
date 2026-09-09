"""Application settings.

The ONLY place environment variables are read. App code imports `settings`;
`os.getenv` / `load_dotenv` anywhere else is a convention violation (see
AGENTS.md). Values come from the environment or a local `.env` file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- core ---
    environment: str = "development"
    log_level: str = "INFO"

    # --- database (Railway Postgres with pgvector) ---
    database_url: str = "postgresql://postgres:postgres@localhost:5432/app"
    """postgresql://... — normalized to the psycopg3 driver in `sqlalchemy_database_url`."""

    # --- redis / celery ---
    redis_url: str = "redis://localhost:6379/0"

    # --- auth (fastapi-users, in this backend) ---
    auth_secret: str = "change-me-in-production"
    """Signs the session JWT + password-reset/verify tokens. Set a long
    random value in production."""
    auth_token_lifetime_seconds: int = 60 * 60 * 24 * 7  # 7 days
    # The token is delivered as an httpOnly cookie (never exposed to JS).
    auth_cookie_name: str = "auth"
    auth_cookie_secure: bool = False
    """True in production (HTTPS only). Keep False for http://localhost."""
    auth_cookie_domain: str | None = None
    """Set to the shared parent domain in production (e.g. '.example.com')
    so the cookie is sent from app.example.com to api.example.com. Leave
    unset for localhost."""
    auth_cookie_samesite: str = "lax"
    """'lax' when the frontend and API share a registrable domain (the
    recommended deployment) — gives CSRF protection for free. Use 'none'
    (with secure=True) only if they are on genuinely different sites, and
    then add CSRF protection."""

    # --- cors ---
    allowed_origins: str = "http://localhost:3000"

    # --- Cloudflare R2 (S3-compatible) ---
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""

    # --- LLM providers (swap provider by config, not code) ---
    llm_provider: str = "openai"
    """Provider for every model call: openai | anthropic | azure | openrouter.

    `openrouter` reaches many vendors through one key, with model ids like
    `anthropic/claude-sonnet-5`. See app/llm/providers.py for what this
    pipeline needs from a model before you point it at an arbitrary one."""
    max_output_tokens: int = 2048
    """Ceiling on a single completion.

    Not a cost control — a correctness one. Providers reserve the full
    `max_tokens` against the account balance *before* generating a token, so
    an unset ceiling (64k on current Claude models) is refused outright
    whenever the remaining balance is smaller than the reservation, whatever
    the request would actually have cost. The error reads exactly like an
    empty account:

        "you requested up to 64000 tokens, but can only afford 59802"

    That was diagnosed as exhausted credit for most of a session while there
    was still money in the account and every call was being refused. A
    decision or a judgement is a few hundred tokens, so a ceiling near the
    work is right independently of billing.
    """
    chat_model: str = "gpt-4.1"
    """Model / deployment name (no provider prefix — llm_provider sets that)."""
    grounding_model: str = "gpt-4.1-mini"
    agent_request_limit: int = 6

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""

    # Azure OpenAI (used when a provider is set to `azure`).
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # --- embeddings (independent provider: Anthropic has no embeddings API) ---
    embedding_provider: str = "voyage"
    """openai | azure | voyage | none. Voyage pairs with a Claude chat stack
    and distinguishes query from document embeddings, which retrieval uses.
    `none` is deliberate and supported: retrieval falls back to Postgres FTS
    alone, which is worse and is not broken."""
    embedding_model: str = "voyage-3.5"
    embedding_dimensions: int = 1024
    """Must match the pgvector column width. Changing it needs a migration
    and a re-embed of every chunk: vectors of different widths cannot be
    compared, and old rows do not silently convert."""
    voyage_api_key: str = ""

    # --- reranking (optional quality step after hybrid retrieval) ---
    rerank_enabled: bool = False
    rerank_candidates: int = 20
    """How many fused candidates to rerank before taking top_k."""

    # --- retrieval ---
    retrieval_candidate_k: int = 30
    retrieval_top_k: int = 8
    retrieval_rrf_k: int = 60
    retrieval_neighbor_radius: int = 1
    retrieval_fts_config: str = "english"

    # --- ingestion ---
    contextual_retrieval: str = "structural"
    """off | structural | llm. What context is prepended to a chunk before
    embedding it (never before storing it). `structural` uses the document
    name and heading path and is free; `llm` generates a sentence per chunk
    and costs a call each."""
    chunk_target_tokens: int = 800
    chunk_overlap_ratio: float = 0.15

    # --- event engine (retries, recovery) ---
    event_max_attempts: int = 3
    """Default attempts before an event is dead-lettered (status=failed)."""
    event_retry_base_delay_seconds: int = 10
    """Exponential backoff base: delay = base * 2^(attempt-1), capped."""
    event_retry_max_delay_seconds: int = 600
    stale_processing_minutes: int = 30
    """An event stuck `processing` longer than this is requeued (or
    dead-lettered) by the sweep — recovers work a crashed worker dropped."""
    stale_sweep_interval_seconds: int = 300
    """How often Celery beat runs the stale-event sweep."""

    # --- webhooks (signed ingress) ---
    webhook_signing_secret: str = ""
    """HMAC-SHA256 secret for verifying inbound webhooks. Empty = reject all."""
    webhook_signature_header: str = "X-Signature-256"
    """Header carrying the signature, format `sha256=<hex>`."""

    # --- rate limiting (Redis fixed-window) ---
    chat_rate_limit: int = 20
    """Max chat turns per user per window (chat is the costly path)."""
    chat_rate_window_seconds: int = 60

    # --- execution (Docket: the system-of-record adapter) ---
    execution_adapter: str = "dry_run"
    """dry_run | email | a client adapter registered in app/adapters/.
    Defaults to dry_run: an unconfigured deployment must do nothing, not
    guess which real system to call."""
    execution_email_to: str = ""
    """Where the email adapter sends approved instructions. Falls back to
    EMAIL_FROM so a misconfigured send is visible rather than silent."""

    # --- email (Resend; no-ops when unset) ---
    resend_api_key: str = ""
    email_from: str = "noreply@example.com"
    frontend_url: str = "http://localhost:3000"
    """Used to build links in password-reset / verification emails."""

    # --- observability (optional; no-ops when unset) ---
    sentry_dsn: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    otel_service_name: str = "docket"
    """Name this deployment reports itself under in traces, and to
    OpenRouter as the calling app."""

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
