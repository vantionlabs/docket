<p align="center">
    <img src="https://raw.githubusercontent.com/vantionlabs/.github/main/profile/banner.png" alt="Vantion Labs" width="100%" />
</p>

<h1 align="center">Docket</h1>

<p align="center">
  <b>Documents checked against your own written policy, and decided.</b><br />
  Clean cases execute themselves. Everything else reaches a person with the reason already written.
</p>

<p align="center">
  <a href="https://github.com/vantionlabs/docket/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/vantionlabs/docket/actions/workflows/ci.yml/badge.svg" /></a>
  <a href="https://www.python.org"><img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="https://fastapi.tiangolo.com"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" /></a>
  <a href="https://github.com/pgvector/pgvector"><img alt="pgvector" src="https://img.shields.io/badge/pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white" /></a>
  <a href="https://docs.celeryq.dev"><img alt="Celery + Redis" src="https://img.shields.io/badge/Celery_+_Redis-DC382D?style=flat-square&logo=redis&logoColor=white" /></a>
  <a href="https://effect.website"><img alt="Effect 4" src="https://img.shields.io/badge/Effect_4-2233f0?style=flat-square" /></a>
  <img alt="0 of 216 nasties released" src="https://img.shields.io/badge/auto--approve_gate-0_of_216_released-2233f0?style=flat-square" />
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/licence-MIT-f4f4f6?style=flat-square" /></a>
  <img alt="Vantion Labs" src="https://img.shields.io/badge/by-Vantion_Labs-2233f0?style=flat-square" />
</p>

---

Documents arrive. Docket reads them, pulls out the fields that matter, checks
them against the client's own written policy, and produces a decision with the
clause that justified it attached.

**The refusal is the product.** Anything can draft an answer. What makes this
sellable is that it knows when it is not allowed to decide, says why, and
escalates, and that every automatic decision carries a citation somebody can
audit a year later.

Built by Vantion Labs as a reference implementation of
the document-to-decision pattern. Invoices against a procurement policy are the
worked example; tenders are the second one, added as configuration.

## How it works

```
document ──▶ extract ──▶ retrieve ──▶ decide ──▶ rails ──┬─▶ auto-approve ─▶ execute
             (fields +   (every       (model)   (code)   │
              source      clause                         └─▶ queue ─▶ a person approves
              spans)      that applies)
```

1. **Extract with provenance.** Every field carries the verbatim span it was
   read from. A field whose span does not verify against the document never
   feeds an automatic action.
2. **Retrieve by coverage, not by top-k.** Retrieval is asked for every policy
   dimension that applies, whether or not the document uses the policy's
   vocabulary. Top-k retrieval fails in two ways and only one is visible: a
   missing clause looks exactly like a satisfied one.
3. **Decide, and cite.** The model chooses clauses, numbers them, then writes
   its reasoning against numbers it has already committed to.
4. **Rails in code.** Arithmetic, duplicate invoice numbers and payment windows
   are checked by code and by the database, never by asking the model. Any
   decision whose citations fail the verbatim check or the judge is downgraded
   to a human.
5. **Auto-approve is a configured rule**, never something the model talks
   itself into. The policy says who may approve; the rule says whether that
   approval can be presumed for a narrow, evidenced class of document.

## What it measured

Numbers from the build notes in [`docs/`](docs/), each with the run behind it.

| | |
|---|---|
| Extraction spans that verified against the document | **5 of 5** documents in the M1 spike |
| Policy clauses retrieved out of those that applied | **1.000 recall** over 99 labelled invoices |
| Cost per decision | **~5¢**, three model calls ($4.78 for 99) |
| Labelled violations that reach auto-approve when the model is assumed wrong | **0 of 216**, with the rule fully armed |
| Pipeline changes needed to add a second document type | **none** (M8) |

Three findings shaped the build more than the numbers did:

- **A missed clause looks like a satisfied one.** A dollar invoice never
  retrieved "invoices are payable in euro", so nothing failed and the output
  looked correct. Retrieval coverage became a first-class measurement, not a
  tuning detail. ([`docs/rag-coverage.md`](docs/rag-coverage.md))
- **40 of 66 grounding failures were bookkeeping, not judgement.** The model
  wrote citation markers before choosing the citations, then reverse-engineered
  a list to match. Declaring citations first cost nothing.
  ([`docs/m5-baseline.md`](docs/m5-baseline.md))
- **A rule whose safety rests on the model being right is not a gate.**
  `evals/check_rule.py` asks, with no model and no database, what a proposed
  rule still stops if the model proposed auto-approve for every invoice,
  including the deliberate nasties. Fully armed, nothing gets through. Armed
  with a spend limit alone, 59 of them do, and the escape ladder separates the
  violations stopped by a mechanism that reads them from the ones stopped only
  by their price: raise the limit to €2,500 and every foreign-currency invoice
  walks through. It runs on every push.

## Status

A reference build, mid-flight and honest about it. M1 through M8 are committed:
the spike, the pipeline, the app, coverage-checked retrieval, the eval harness,
the auto-approve gate and the second vertical. 339 tests passed at the M6
commit; the two that fail are end-to-end model runs blocked on API credit.

Not done: the full grading run that would license arming auto-approve in
production, a real system-of-record connector (only `DryRunAdapter` and
`EmailAdapter` exist), and a deploy. See [`docs/roadmap.md`](docs/roadmap.md).

## The screens

- **`/queue`** is the product. Keyboard-first: `j`/`k` move, `a` approves, `r`
  rejects. Each row says in one line why it needs a person.
- **`/decisions/{id}`** is the demo. The document on the left, extracted fields
  with their source spans in the middle, cited policy clauses on the right.
  Clicking a field highlights its span, matched exactly the way the backend's
  verbatim check matches it.
- **`/audit`** is boring, and is the reason a finance director signs. One row
  per decision with citation count, who approved, and what the adapter
  returned. CSV export, because that is what gets sent to an auditor.
- **`/rules`** and **`/replay`**: what may be presumed, and what a proposed
  rule would have done to decisions already made.

## Running it

```bash
docker compose up -d postgres redis

cd backend
cp .env.example .env          # OPENROUTER_API_KEY or OPENAI_API_KEY, R2_* for uploads
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
uv run celery -A app.worker.celery_app worker --loglevel=INFO   # another terminal

cd ../web && pnpm install && pnpm dev                            # the app
```

```bash
uv run pytest -m "not integration"      # offline: no database, no network
uv run ruff check .
uv run python evals/check_rule.py --strict   # what a rule stops when the model is wrong
uv run python evals/run_decision_eval.py     # the graded set (needs a model)
```

## Layout

| Path | What is in it |
|---|---|
| `backend/app/` | FastAPI, the workflow engine, extraction, retrieval, rails, adapters |
| `backend/evals/` | The labelled decision set, the rule checker, the harnesses |
| `backend/migrations/` | Alembic owns the whole schema |
| `web/` | The TypeScript app (Effect v4 monorepo) that owns the product surface |
| `frontend/` | The earlier Next.js app, kept as the reference while `web/` catches up |
| `docs/` | Build notes, one per milestone, and the architecture |
| `docket-spec.md` | The spec, written before any code existed |

Python keeps inference; TypeScript owns auth, orgs, permissions and the product
surface. `web/repos/` vendors Effect at a pinned version on purpose: the source
is the authority over recall, which only holds while it matches what is
installed.

## What it deliberately does not do

- No multi-step approval chains. Two sequential approvals are two rows.
- No connector to a real accounting system until a client has one.
- No arithmetic by model. A model asked to add up a column will sometimes add
  it up wrong.
- No auto-approval without a configured rule, whatever the model proposes.

## Contributing

Issues and pull requests are welcome, especially eval cases that catch a real
failure. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and
[AGENTS.md](AGENTS.md); security reports go through a private GitHub security advisory, see
[SECURITY.md](SECURITY.md).

## Licence

MIT. See [LICENSE](LICENSE). The vendored Effect source under `web/repos/`
keeps its own licence. Built by Vantion Labs.
