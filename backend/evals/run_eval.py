"""RAG eval / regression harness.

Runs a fixed question set through the real pipeline (ingest → retrieve →
grounded agent → validate) and scores three things:

  - retrieval:  did the expected source document appear in the retrieved
                chunks? (a recall proxy)
  - answer:     does the answer contain an expected substring, OR correctly
                report insufficient evidence when it should?
  - grounding:  did the answer pass citation validation?

Prints a per-case table + summary, and exits non-zero if the pass rate is
below `--threshold` — so it doubles as a CI regression gate.

Usage (needs a running Postgres + OPENAI_API_KEY, i.e. real services):
    uv run python evals/run_eval.py
    uv run python evals/run_eval.py --dataset evals/dataset.example.jsonl --threshold 0.8

This is intentionally simple. For richer scoring, add an LLM grader (compare
answer to a reference) — the seam is `score_answer` below.
"""

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

# Make `app` importable when run from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.agent import run_turn  # noqa: E402
from app.agent.deps import AgentDeps  # noqa: E402
from app.db.engine import SessionLocal  # noqa: E402
from app.db.models import DocumentStatus, SourceDocument, User  # noqa: E402
from app.grounding.turn_registry import TurnRegistry  # noqa: E402
from app.grounding.validator import validate  # noqa: E402
from app.ingestion.chunking import chunk_text  # noqa: E402
from app.retrieval.embeddings import embed_batch  # noqa: E402
from app.retrieval.hybrid import hybrid_search  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class Case:
    question: str
    expect_substrings: list[str]
    expect_filename: str | None
    expect_insufficient: bool


def load_cases(path: Path) -> list[Case]:
    cases = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        cases.append(
            Case(
                question=d["question"],
                expect_substrings=d.get("expect_substrings", []),
                expect_filename=d.get("expect_filename"),
                expect_insufficient=d.get("expect_insufficient", False),
            )
        )
    return cases


def seed_corpus(db, user_id: uuid.UUID) -> None:
    """Ingest the fixture documents directly (bypassing R2/Celery) so the
    eval is self-contained."""
    for md in FIXTURES.glob("*.md"):
        existing = db.query(SourceDocument).filter_by(user_id=user_id, filename=md.name).first()
        if existing:
            continue
        doc = SourceDocument(
            user_id=user_id,
            filename=md.name,
            r2_key=f"eval/{md.name}",
            content_type="text/markdown",
            status=DocumentStatus.processing,
        )
        db.add(doc)
        db.flush()
        chunks = chunk_text(md.read_text())
        vectors = embed_batch([c.content for c in chunks])
        from app.db.models import DocumentChunk

        db.add_all(
            DocumentChunk(
                document_id=doc.id,
                user_id=user_id,
                chunk_index=c.index,
                content=c.content,
                embedding=v,
            )
            for c, v in zip(chunks, vectors, strict=True)
        )
        doc.status = DocumentStatus.ready
    db.commit()


def score_answer(case: Case, answer: str, insufficient: bool) -> bool:
    if case.expect_insufficient:
        return insufficient
    if insufficient:
        return False
    if not case.expect_substrings:
        return True
    lower = answer.lower()
    return any(s.lower() in lower for s in case.expect_substrings)


def run(dataset: Path, threshold: float) -> int:
    cases = load_cases(dataset)
    eval_user = uuid.uuid4()

    with SessionLocal() as db:
        # A throwaway user owns the eval corpus (FK requires a real row).
        db.add(User(id=eval_user, email=f"eval+{eval_user}@local", hashed_password="x"))
        db.commit()
        seed_corpus(db, eval_user)

    rows, retr_ok, ans_ok, grnd_ok = [], 0, 0, 0
    for case in cases:
        registry = TurnRegistry()
        deps = AgentDeps(user_id=eval_user, registry=registry)
        answer = run_turn(case.question, [], deps)
        validation = validate(answer, registry, eval_user)

        retrieved = hybrid_search(eval_user, case.question)
        filenames = {c.filename for c in retrieved}
        retrieval_hit = case.expect_filename in filenames if case.expect_filename else True
        answer_hit = score_answer(case, answer.answer, answer.insufficient_evidence)

        retr_ok += retrieval_hit
        ans_ok += answer_hit
        grnd_ok += validation.ok
        rows.append((case.question[:48], retrieval_hit, answer_hit, validation.ok))

    print(f"\n{'question':50} retr ans grnd")
    print("-" * 68)
    for q, r, a, g in rows:
        print(f"{q:50} {_m(r)}   {_m(a)}   {_m(g)}")
    n = len(cases)
    print("-" * 68)
    print(f"retrieval {retr_ok}/{n}  answer {ans_ok}/{n}  grounding {grnd_ok}/{n}")

    pass_rate = ans_ok / n if n else 0.0
    print(f"\nanswer pass rate: {pass_rate:.0%} (threshold {threshold:.0%})")
    return 0 if pass_rate >= threshold else 1


def _m(ok: bool) -> str:
    return " ok " if ok else "FAIL"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(Path(__file__).parent / "dataset.example.jsonl"))
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()
    raise SystemExit(run(Path(args.dataset), args.threshold))
