# Contributing

Thanks for helping. Docket is a reference build: it exists to show how a
document-to-decision pipeline can be trusted with real money, so the bar for a
change is whether it makes a decision easier to audit, not whether it makes the
demo look better.

## Good contributions

- Bug fixes in extraction, retrieval coverage, the rails or the citation checks.
- Eval cases that catch a real failure. `backend/evals/decisions.jsonl` is the
  labelled set; a case that the pipeline gets wrong is more useful than a case
  it gets right.
- A new vertical (`backend/app/`, see M8): a schema, dimensions, a query, a
  renderer, triggers, subject terms and checks. If adding one needs a change to
  the pipeline itself, that is a bug in the pipeline and worth an issue.
- Adapters for a real system of record, built against the existing port.
- Docs that were wrong or missing when you set it up.

Open an issue before something larger, such as approval chains or a second
frontend.

## Making a change

1. Read [AGENTS.md](AGENTS.md) and `backend/AGENTS.md`. The conventions apply
   to human and agent changes alike: env vars are read in one place, arithmetic
   is computed in code rather than by a model, and there is one verbatim check.
2. Run the checks:

   ```bash
   cd backend
   uv run ruff check .
   uv run pytest -m "not integration"        # offline: no database, no network
   uv run python evals/check_rule.py --strict  # free, no model needed

   cd ../web
   pnpm lint && pnpm check && pnpm test
   ```

   CI runs the same. `ruff format` is deliberately not enforced: the repository
   is not formatter-clean and reformatting it would bury the history.

3. If your change moves a published number, update the table in
   [README.md](README.md) and the note in `docs/` that produced it. A number
   without the run behind it is not a number.

## What needs a measurement, not an opinion

Changes to prompts, retrieval or the rails are judged by the eval, not by
reading the diff. `evals/check_rule.py` runs without a model and answers "what
does this rule still stop when the model is wrong". Say what it printed before
and after.
