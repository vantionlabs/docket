# forge

A starting point for multi-tenant SaaS: sign-in, organizations, roles and
permissions, an audit trail, API keys and a public HTTP API — already wired
together, already tested, already deployable.

It is deliberately not a framework. There is no `forge.config.ts` to learn and
nothing generates code. It is an ordinary Effect v4 monorepo with one worked
example of a tenant-owned feature (`Contact`), which you delete and replace with
your own.

```
apps/server     Effect API — RPC for the app, HTTP for the public API and auth
apps/web        TanStack Start front end
packages/domain the contract both ends compile against
packages/database   connection, row-level security, migrations
```

Dependencies point one way, from `apps/` into `packages/`. Both apps compile
against the same schemas, so a change to a payload breaks the client at build
time rather than in production.

## What you get

**Identity** — email and password, magic link, email OTP, and Google, via
[better-auth](https://better-auth.com). Every new user gets a personal
organization on creation, so there is no orgless state anywhere else in the
system to represent or handle.

**Organizations and access control** — members, invitations, the built-in
`owner`/`admin`/`member` roles, plus custom roles and per-member overrides
editable in the UI. One permission model, declared once in
`packages/domain/src/iam/Permission.ts`, is what both our RPC policies and
better-auth's own endpoint checks are built from — so the two cannot quietly
disagree about who may do what.

**Tenant isolation, twice** — Postgres row-level security on tenant tables, and
`withOrgScope` around the queries that touch them. Neither is trusted alone.

**An audit trail** — writes record who did what, browsable at
`/settings/audit`.

**A public API** — `/api/v1`, authenticated by API key rather than by session,
with an OpenAPI document at `/api/v1/openapi.json` and browsable docs at
`/api/v1/docs`. It runs over the same stores as the RPC, so a handler is never
written twice. Keys are created and revoked at `/settings/api-keys`.

**A front end that is already an app** — sidebar, org switcher, command palette,
breadcrumbs, error boundaries, empty states, light and dark. shadcn components
on [Base UI](https://base-ui.com). Server-rendered auth: `beforeLoad` resolves
the session before the page renders, so protected routes never flash.

**Operations** — `/health` and `/ready`, OpenTelemetry tracing, a Dockerfile per
app, and Railway infrastructure as code.

## Getting started

You need Node 22+, pnpm, and Postgres. (`docker compose up -d` gives you the
database if you would rather not run one.) A Nix flake is included but optional.

```bash
pnpm install
cp .env.example .env
```

Fill in `AUTH_SECRET` — `openssl rand -base64 32` — and point `DATABASE_URL` at
your database. Everything else has a working local default.

Apply the schema — the migration runner reads the same `.env` — then start both
servers:

```bash
pnpm --filter @forge/database migrate
```

```bash
pnpm dev
```

The API is on `http://localhost:3000` and the front end on
`http://localhost:5173`. Sign up with an email and password — nothing blocks
sign-in on verification, so you are straight in with your own organization.

Email needs no setup to try. Without `RESEND_API_KEY`, the mailer writes each
message to the server log instead of sending it — so a magic link is a link you
can follow out of your terminal, and every auth flow works on a fresh clone.
Set the key when you want mail to actually leave.

## Making it yours

**Rename.** The package scope is `@forge/*` and appears in imports throughout.
One pass does it:

```bash
grep -rl '@forge/' --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=repos . | xargs perl -pi -e 's|\@forge/|\@acme/|g'
```

Then the loose ends: `name` in each `package.json`, the database name in
`docker-compose.yml` and `.env`, `OTEL_SERVICE_NAME`, `EMAIL_FROM`, and the repo
and project name in `.railway/railway.ts`.

**Delete the example.** `Contact` is a worked example of a tenant-owned entity
and nothing else depends on it being contacts specifically. It is these files,
plus its rows in `Permission.ts` and its route in the sidebar:

```
packages/domain/src/contact/ContactRpc.ts
apps/server/src/contact/
apps/web/src/atom/contact-atoms.ts
apps/web/src/components/contact/
apps/web/src/routes/_protected/contacts.tsx
```

Read it before you delete it — it is the shortest description of how a feature
is put together here.

**Adjust permissions.** `packages/domain/src/iam/Permission.ts` declares the
resources and actions, and `grantsFor` says which role gets what. The
`organization`, `member`, `invitation` and `team` entries are better-auth's own
vocabulary and should stay as they are; add yours alongside `contact`. The
picker in the UI and better-auth's access control are both generated from this
declaration, so adding a resource is a one-line change that shows up in both.

## Adding a feature

A tenant-owned feature is five files and a migration, in this order:

1. **A migration** in `packages/database/src/migrations/`. Give the table an
   `organizationId`, and copy the row-level-security policy from `0002_rls.sql`.
   Migrations are idempotent and there is no ledger — applying the whole set to
   any database converges it on the committed schema, and
   `packages/database/test/Migrations.test.ts` keeps that honest by applying
   them twice.

2. **The contract** in `packages/domain/`, an `RpcGroup` of `Rpc.make` calls
   ending in `.middleware(AuthMiddleware)`. Merge it into `AppRpcs` — both ends
   read that list, so a group added to one and not the other is a compile error
   rather than a call that fails at runtime.

3. **A store** in `apps/server/`, wrapping its queries in `withOrgScope`.

4. **The handlers**, `YourRpcs.toLayer(...)`, guarded with `withPolicy` and
   `permission(...)`. Provide the layer in `apps/server/src/Main.ts`.

5. **Atoms** in `apps/web/src/atom/`. Reads are declared by naming the RPC —
   `AppRpc.query("ListThings", undefined, { reactivityKeys })` — and writes stay
   hand-written as `AppRpc.runtime.fn`, which keeps "what does this invalidate"
   next to the write rather than at every call site.

Only step 4 is where you decide anything about authorization, and only step 1 is
where you decide anything about isolation. The rest is transport.

To expose it publicly as well, add it to `packages/domain/src/api/v1/Api.ts` and
implement it in `apps/server/src/api/v1/Handlers.ts` over the same store. Read
`Wire.ts` first — it is the frozen contract and it explains what may change in
it.

## Deploying

`pnpm build` produces the API bundled to `apps/server/build/bundle/main.js`, the
web app's Nitro output in `apps/web/.output/`, and the migration runner with its
`.sql` files beside it. The API is bundled rather than merely compiled because
the workspace packages export TypeScript source, which `tsc` output alone would
import as `.ts` files Node cannot load.

Each app has its own Dockerfile, built from the repo root:

```bash
docker build -f apps/server/Dockerfile -t acme-api .
```

Migrations are applied by a script, never at boot — two instances starting
together would both migrate. On Railway that is the `preDeployCommand`.

`.railway/railway.ts` describes the whole project: database, both services,
their variables and health checks. `railway config plan` shows the diff and
`railway config apply` performs it, so a deployment is reviewable the way a pull
request is. Change `REPO`, the `environments` map and the project name; secrets
stay in Railway's dashboard, held by `preserve()`.

Branch and domain come from the environment being planned against, via
`ctx.isEnvironment`, so production and staging can differ without the file
depending on whoever runs it. `process.env` is readable in that runner, but
reaching for it would cost the property that makes a plan worth reviewing: two
people planning the same environment get the same plan.

It cannot create the domains, though — the runner rejects a `domains` entry
outright, so both services need theirs added in the dashboard. Setting `DOMAIN`
is what makes every address in the file name them ahead of time rather than
falling back to a `RAILWAY_PUBLIC_DOMAIN` that does not resolve yet.

**One constraint to know before you pick hostnames.** The browser talks to the
API directly, so the two are separate origins and the session cookie only flows
between them if they are _same-site_: both under one parent domain, with
`AUTH_COOKIE_DOMAIN=.example.com`. That parent cannot be a public suffix, and
`up.railway.app` is on the list — so **two generated Railway hosts can never
share a session**. Splitting these services there needs a domain of your own,
`app.example.com` and `api.example.com`.

Tracing exports only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Leaving it unset
installs no exporter at all, because one pointed at nothing retries on a
schedule and fills the log.

## Commands

|                                |                                                     |
| ------------------------------ | --------------------------------------------------- |
| `pnpm dev`                     | API and front end together                          |
| `pnpm build`                   | deployable artifacts for every package              |
| `pnpm check`                   | `tsc -b` across all project references              |
| `pnpm lint`                    | oxlint, including Effect type-aware and local rules |
| `pnpm format` / `format:check` | dprint                                              |
| `pnpm test`                    | vitest across `apps/*` and `packages/*`             |

Postgres-backed tests skip without a database. Either `docker compose up -d`, or
point at an existing instance with `TEST_DB_URL=postgresql://...`.

## Reading further

`AGENTS.md` is the map — layout, commands, and the deployment story, written for
whoever (or whatever) picks the repo up cold. `RULES.md` holds the hard rules on
Effect style, architecture, forms, observability and testing; read it before
changing much. `knowledge/README.md` indexes the per-topic guides.

`repos/` vendors the Effect and effect-form sources at exactly the versions this
repo depends on. Effect v4 is a release candidate whose APIs moved recently, so
read the real signature there rather than trusting recall — including your own.
