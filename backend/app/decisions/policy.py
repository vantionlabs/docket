"""The policy corpus: the client's own written rules, kept separate.

Spec section 8. The decision is grounded in policy, never in the document
being decided, so these two bodies of text must not be able to reach each
other. In the built pipeline that separation is a `collection` column on
`source_documents` and a filter in `hybrid_search`. Here in the M1 spike
it is simpler and stricter: the policy is a markdown file loaded into
memory, and the invoice is never in it.

Retrieval is lexical, deliberately. The spike exists to find out whether
extraction and the policy check hold up on real documents, and pgvector
plus an embedding bill would not make that question easier to answer.
M2 swaps `PolicyCorpus.retrieve` for `hybrid_search(..., collection="policy")`
and nothing above it changes.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the to with".split()
)


@dataclass(frozen=True)
class PolicyClause:
    id: str
    """Stable within a corpus load, and what a citation must name."""
    ref: str
    """Human-readable reference, e.g. '4.2 Spend thresholds'."""
    text: str
    """The clause body, heading included, exactly as written."""

    def cite_block(self) -> str:
        return f"[{self.id}] {self.ref}\n{self.text}"


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1]


class PolicyCorpus:
    """A markdown policy file, split into citable clauses."""

    def __init__(self, clauses: list[PolicyClause]) -> None:
        self.clauses = clauses
        self._by_id = {c.id: c for c in clauses}
        self._tokens = {c.id: Counter(_tokens(c.text)) for c in clauses}
        total = len(clauses) or 1
        seen = Counter()
        for counts in self._tokens.values():
            seen.update(counts.keys())
        self._idf = {word: math.log(1 + total / (1 + count)) for word, count in seen.items()}

    @classmethod
    def from_markdown(cls, text: str) -> "PolicyCorpus":
        """Split on headings. Each heading and its body is one clause."""
        clauses: list[PolicyClause] = []
        heading: str | None = None
        body: list[str] = []

        def flush() -> None:
            if heading is None:
                return
            content = "\n".join([heading, *body]).strip()
            if not content:
                return
            ref = _HEADING.match(heading).group(2).strip()  # type: ignore[union-attr]
            clauses.append(PolicyClause(id=f"clause-{len(clauses) + 1}", ref=ref, text=content))

        for line in text.splitlines():
            match = _HEADING.match(line)
            if match:
                flush()
                heading, body = line, []
            elif heading is not None:
                body.append(line)

        flush()
        return cls(clauses)

    @classmethod
    def from_path(cls, path: str | Path) -> "PolicyCorpus":
        return cls.from_markdown(Path(path).read_text(encoding="utf-8"))

    def get(self, clause_id: str) -> PolicyClause | None:
        return self._by_id.get(clause_id)

    def __contains__(self, clause_id: str) -> bool:
        return clause_id in self._by_id

    def retrieve(self, query: str, top_k: int = 8) -> list[PolicyClause]:
        """The clauses most likely to bear on `query`, best first."""
        wanted = set(_tokens(query))
        if not wanted:
            return list(self.clauses[:top_k])

        scored: list[tuple[float, PolicyClause]] = []
        for clause in self.clauses:
            counts = self._tokens[clause.id]
            score = sum(
                self._idf.get(word, 0.0) * math.log(1 + counts[word])
                for word in wanted
                if word in counts
            )
            if score > 0:
                scored.append((score, clause))

        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [clause for _, clause in scored[:top_k]]
