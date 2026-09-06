# AI quality: providers, reranking, evals

The three levers that separate a serious RAG build from prompt-and-pray.

## Provider-agnostic LLM (OpenAI / Anthropic / Azure)

Provider choice is **per capability**, not global — you rarely want
"everything Claude" (Anthropic has no embeddings API). Three independent
knobs, all config:

| Capability | Setting | Providers |
| --- | --- | --- |
| Agent (generation) | `LLM_PROVIDER` + `CHAT_MODEL` | openai · anthropic (Claude) · azure |
| Grounding judge + reranker | `LLM_PROVIDER` + `GROUNDING_MODEL` | same |
| Embeddings | `EMBEDDING_PROVIDER` + `EMBEDDING_MODEL` | openai · azure (add Voyage/Cohere in `app/llm/embeddings.py`) |

Models are built in ONE place — `app/llm/providers.py` — with keys passed
explicitly from settings (so `.env` alone works; no reliance on process env).
The agent, the grounding judge, and the reranker all go through it, so a
provider swap never touches code.

```bash
# Claude for generation, OpenAI for embeddings (Anthropic has none):
LLM_PROVIDER=anthropic
CHAT_MODEL=claude-sonnet-4-0
ANTHROPIC_API_KEY=...
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=...

# All-Azure (EU tenant, enterprise):
LLM_PROVIDER=azure
CHAT_MODEL=<your-deployment-name>
AZURE_OPENAI_ENDPOINT=https://<res>.openai.azure.com
AZURE_OPENAI_API_KEY=...
EMBEDDING_PROVIDER=azure
EMBEDDING_MODEL=<embedding-deployment-name>
```

Keep the cost table in `app/observability/usage.py` in sync with the models
you actually use.

## Reranking

Hybrid retrieval (vector + FTS + RRF) is recall-oriented — it casts a wide
net. **Reranking** re-scores those candidates for precision and keeps the
best; it's the single biggest quality lever for RAG.

Off by default (it adds one model call per query). Turn on:

```bash
RERANK_ENABLED=true
RERANK_CANDIDATES=20   # fused candidates to rerank before taking top_k
```

The default reranker (`app/retrieval/rerank.py`) scores candidates 0-10
through the same provider abstraction, so it works with any provider and
needs no extra deps. For lower latency/cost at scale, swap that one function
for a cross-encoder (sentence-transformers, a `[rerank]` extra) or a hosted
reranker (Cohere, Voyage, Jina). Retrieval falls back to the fused order if
reranking errors.

## Evals (regression gate)

`backend/evals/` runs a fixed question set through the real pipeline and
scores retrieval, answer correctness, and grounding — exiting non-zero below
a threshold so it can gate CI. This is what lets you swap a model or tweak a
prompt and *prove* you didn't regress answer quality.

```bash
uv run alembic upgrade head
uv run python evals/run_eval.py --threshold 0.8
```

Add cases to `evals/dataset.example.jsonl`, drop real client docs in
`evals/fixtures/`, and see `evals/README.md` to extend the scoring (e.g. an
LLM grader against reference answers).
