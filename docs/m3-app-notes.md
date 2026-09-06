# M3 notes: the app, and what running it found

M3 is spec section 16's "the app": orgs and roles, the review queue, the
decision detail screen, the audit log, rules. Verified in a browser against
a real database, a real worker and a real model on 6 September 2026.

153 offline tests, 8 integration tests, ruff clean, frontend builds.

## The four screens

**`/queue`** is the product. Keyboard-first: `j`/`k` move, `a` approves,
`r` rejects, Enter opens. A row leads with the supplier and the amount,
then says in one line why it needs a person. Header carries pending,
executed, auto-approved share and override rate.

**`/decisions/{id}`** is the demo. Document left, extracted fields with
their source spans middle, cited policy clauses right. Clicking a field
highlights its span in the document, matched the way the backend's
verbatim check matches it: whitespace-collapsed and case-insensitive,
nothing else normalized. Highlighting text the check would have rejected
would be worse than highlighting nothing.

**`/audit`** is boring and is the reason a finance director signs. One row
per decision with the citation count, who approved, and what the adapter
returned. CSV export, because that is what gets sent to an auditor.

**`/settings/rules`** is rail 3's gate. Owner-only. The auto-approve toggle
says what it does in as many words rather than looking like any other
setting.

## What running it found

**Field order was JSONB key order.** The detail screen showed `due_on`
above `supplier` and buried `total_incl_vat` under fifteen line-item
components, because Postgres JSONB does not preserve key order and nothing
imposed the schema's back onto it. Fixed with a schema registry
(`app/extraction/schemas/__init__.py`) that M4's second vertical needs
anyway.

**Queue rows led with a developer string.** Every stalled row said
"Grounding failed: judge rejected citations [1]", which is true, precise,
and useless to somebody clearing a queue. Rows now lead with the supplier
and amount, and the rail notes are written for a reviewer: "A policy clause
was quoted correctly but does not support the claim it was attached to, so
the reasoning does not hold up. Read the clauses yourself."

**A 500 rendered as "Not found".** Moving `filename` onto the shared
summary made the detail endpoint pass it twice, and the UI showed the
resulting 500 exactly like a missing decision. Two fixes: the endpoint
builds its payload from the same summary the queue uses, and the screen
distinguishes "not found" from "could not load". A test now covers the
endpoint, which had none.

## The open problem: escalation rate

Three of five seeded invoices land in `needs_human` because the judge
rejects a citation. The system is behaving as designed, fail-closed, and
the rail notes explain it well. The economics are still wrong: section 13
says false escalation is the cost number, and 60 percent is a bad one.

Diagnosis so far. The judge was rejecting citations whose claims it could
not verify arithmetically, which is not its job: arithmetic is checked in
code before it ever sees a decision. Its prompt now says to judge subject
relevance only, explicitly not amounts, dates or thresholds. After that
change the failures became consistent rather than scattered: they are the
opening claim of the rationale, where the model attaches a policy clause to
a fact about the document ("the invoice carries PO-2026-0088"). No clause
supports a fact about the invoice, so the judge is right to reject it, and
the decision instructions now say not to mark those claims. The model still
does it.

**This is where the tuning stops and the eval harness starts.** Every
change above was measured on one run of five documents, which is not a
measurement. Section 13's harness is the next thing to build, and the first
number it should report is not accuracy but the escalation rate broken down
by cause: ungrounded, unverified field, arithmetic, rule.

## Running it

```bash
docker run -d --name docket-postgres -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=app -p 55432:5432 \
  pgvector/pgvector:pg17
docker run -d --name docket-redis -p 56379:6379 redis:7-alpine

cd backend
export DATABASE_URL=postgresql://postgres:postgres@localhost:55432/app
export REDIS_URL=redis://localhost:56379/0
uv run alembic upgrade head
uv run python scripts/seed_demo.py          # demo@northwind.nl / docket-demo
uv run uvicorn app.main:app --port 8000 &
uv run celery -A app.worker.celery_app worker --loglevel=INFO &

cd ../frontend && pnpm dev                   # http://localhost:3000
```

The compose file is still the intended path; the standalone containers are
here because this machine's Docker had no address pools left for a new
compose network, and because port 5432 was already taken.

## Still open

- **Deploy to Railway.** Section 16 lists it under M3 and it has not been
  done. `docs/setup-railway.md` and `backend/railway.json` come from the
  template and have not been exercised for this app.
- **Embeddings.** Retrieval calls `embed_query` unconditionally, so an
  install with no embedding provider cannot retrieve at all. The seed script
  and the integration tests stub it to zeros and lean on Postgres FTS. That
  is a demo posture, not a deployment one, and whether `hybrid_search`
  should degrade to FTS-only rather than raise is a decision that deserves
  more care than a fallback added in passing.
- **Org switching.** One org per user. `active_membership` is the single
  function that has to learn about a switcher when a user can belong to
  several, and nothing above it changes.
