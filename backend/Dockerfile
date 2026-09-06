# Backend image: serves BOTH the API and the Celery worker.
# Railway runs two services from this one image with different start
# commands (see docs/setup-railway.md):
#   api:    uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
#   worker: uv run celery -A app.worker.celery_app worker --loglevel=INFO
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Dependency layer (cached until pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code.
COPY . .
RUN uv sync --frozen --no-dev

CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
