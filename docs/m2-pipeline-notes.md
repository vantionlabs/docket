# M2 notes: what the pipeline does, and what building it found

M2 is spec section 16's "the pipeline": migrations, the two workflows, the
router, the repointed validator, `DryRunAdapter`, and the approve endpoint.
Everything queues; nothing auto-approves.

Verified on 6 September 2026 against Postgres 17 with pgvector 0.8.6 and
`claude-sonnet-5`. 124 offline tests, 8 integration tests, ruff clean.

## The shape

```
document.decide (seconds, never waits)        decision.execute
  LoadDocument                                  CheckIdempotency
  FetchFromR2                                   CallAdapter
  ParseDocument                                 RecordExecution
  ExtractFields      -> extractions row         NotifySubmitter
  DecideAgainstPolicy                                  ^
  ApplyRails         -> decisions row                  |
  RouteOutcome ---- auto ---> EmitExecute -------------+
       |                                               |
       +--------- else ---> Done                       |
                              (decisions.pending_review)|
                                    POST /approve ------+
```

Two workflows, joined by an event. The decide workflow ends by writing a
row and returning; the `events` row is the durable checkpoint, so a pending
decision is something anyone can query rather than a suspended coroutine
somebody has to trust.

## What building it found

**An uncited `route_for_approval` was shipping.** The citation check only
demanded citations for `auto_approve` and `reject`. A live integration run
produced a `route_for_approval` with no `[n]` markers and no citations
roughly one time in four, and it passed grounding: a decision with no
policy basis, which is the one thing this pipeline exists to prevent.

Fixed by requiring citations for every outcome except `needs_human`.
`route_for_approval` is a policy claim too ("policy permits this, but
someone must sign off"), and only declining to decide needs no policy
support. An uncited decision now fails grounding, which rail 1 turns into
`needs_human` with the reason attached. The refusal is the product.

This is the second time a live run found something no unit test would
have: the first was the currency clause in M1. Both were cases where the
output looked correct and was not.

**Flaky assertions are a design smell.** The test that caught it was
asserting on model output ("there are citations"), which is not something
the system guarantees. It now asserts the invariant the rails do guarantee:
every outcome except `needs_human` has at least one citation, whatever the
model returns. Span verification moved the same way, from a pass/fail
assertion to the rail it feeds ("an unverified field can never
auto-approve"). Quality belongs in the eval harness, section 13; invariants
belong in tests.

## Running it

```bash
docker run -d --name docket-postgres \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=app \
  -p 55432:5432 pgvector/pgvector:pg17
cd backend
export DATABASE_URL=postgresql://postgres:postgres@localhost:55432/app
uv run alembic upgrade head
uv run pytest -m "not integration"   # offline, no services
uv run pytest -m integration         # needs the database above and an LLM key
```

The compose file is the intended path and still works where Docker can
create a network. On the machine this was built on the address pools were
exhausted by other projects, hence the standalone container on port 55432.

## Deliberately not done in M2

- **Orgs are schema only.** `organizations` and `memberships` exist and
  `org_id` is on every domain table, nullable. Nothing sets it and the auth
  seam still scopes on `user_id`. M3 wires it. Creating the columns now
  means the tables are never rewritten under live data; leaving them
  nullable is honest about the fact that nothing populates them yet.
- **No Celery worker in the integration tests.** They run the workflows
  directly. Retries, dead-lettering and stale recovery are the template's
  and are already covered by `tests/test_reliability.py`; what M2 adds is
  the domain either side of them.
- **Retrieval ranking is not under test.** The end-to-end test stubs
  embeddings to zeros and leans on Postgres FTS, because this machine has
  an Anthropic key and no embedding provider. The plumbing is real, the
  ranking is not. Recall belongs in the eval harness, and after M1 it is a
  first-class metric there.
