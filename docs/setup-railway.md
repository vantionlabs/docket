# Railway deployment

Five services in one Railway project. Deploy the repo (or the copied-out
client repo) with these root directories and commands.

## 1. Postgres (pgvector)

Add the **pgvector** template image (`pgvector/pgvector:pg17`) rather than
the default Postgres, so `CREATE EXTENSION vector` works. Note the
`DATABASE_URL` it exposes.

## 2. Redis

Add Railway's Redis. Note `REDIS_URL`.

## 3. API (backend)

- Root directory: `backend` (Dockerfile is picked up automatically).
- `railway.json` runs `uv run alembic upgrade head` pre-deploy. Point the
  healthcheck at `/health/ready` (checks Postgres + Redis) so a broken
  dependency stops traffic.
- Variables: everything from `backend/.env.example` — `DATABASE_URL`,
  `REDIS_URL`, `AUTH_SECRET`, `AUTH_COOKIE_SECURE=true`, `AUTH_COOKIE_DOMAIN`
  (shared parent domain), `ALLOWED_ORIGINS` (frontend URL), `OPENAI_API_KEY`,
  `R2_*`.

## 4. Worker

- Same root directory `backend`, same image.
- Override the start command (the `-B` runs Celery beat embedded, so the
  stale-event sweep and any scheduled jobs run):
  `uv run celery -A app.worker.celery_app worker -B --loglevel=INFO`
- Same variables as the API (share a variable group). No healthcheck.
- At scale, run a **dedicated beat service** instead of `-B`
  (`uv run celery -A app.worker.celery_app beat`) so multiple workers don't
  each schedule the jobs.
- If you accept webhooks, set `WEBHOOK_SIGNING_SECRET` on the API service.

## 5. Frontend

- Root directory: `frontend`.
- `NEXT_PUBLIC_API_URL` must be set as a BUILD-time variable (it's baked
  into the bundle).
- Runtime variable: `NEXT_PUBLIC_API_URL` is the only one the frontend
  needs (and it is build-time, above). Auth lives in the backend — the
  frontend holds no secrets.

Set the API service's `AUTH_COOKIE_SECURE=true`, `AUTH_COOKIE_DOMAIN` to the
shared parent domain (e.g. `.client.com`), and `ALLOWED_ORIGINS` to the
frontend's public URL. Deploy the frontend and API under that one domain
(`app.client.com` + `api.client.com`) so the SameSite=Lax session cookie
works (see setup-auth.md).

## Order of operations (fresh project)

1. Postgres (pgvector) + Redis up.
2. Deploy API (Alembic pre-deploy creates the full schema, including the
   `users` table).
3. Deploy worker.
4. Deploy frontend under the same parent domain as the API.
5. Set the R2 bucket CORS to the frontend's public origin (see setup-r2.md).
