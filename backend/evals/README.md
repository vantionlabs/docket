# Evals

A regression gate for the RAG pipeline. Prompt-and-pray doesn't survive
client scrutiny; this proves the pipeline still answers correctly after a
prompt tweak, a model swap, or a retrieval change.

## Run

Needs a real Postgres (pgvector) and an LLM key — it exercises the full
pipeline end to end.

```bash
docker compose up -d postgres              # or point DATABASE_URL anywhere
uv run alembic upgrade head
uv run python evals/run_eval.py            # exits non-zero if below threshold
uv run python evals/run_eval.py --threshold 0.9
```

It ingests the fixture docs in `fixtures/` for a throwaway user, runs each
question through retrieval + the grounded agent + validation, and scores:

- **retrieval** — did the expected source document surface?
- **answer** — does the answer contain an expected substring (or correctly
  report insufficient evidence)?
- **grounding** — did citation validation pass?

## Extend

- Add cases to `dataset.example.jsonl` (one JSON object per line):
  `{"question", "expect_substrings"[], "expect_filename", "expect_insufficient"}`.
- Drop real client documents in `fixtures/` and write cases against them.
- For stricter answer scoring, replace `score_answer` in `run_eval.py` with
  an LLM grader that compares the answer to a reference.
- Wire it into CI to block merges that regress answer quality.
