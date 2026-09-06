"""The policy corpus: the client's own written rules, kept separate.

Spec section 8. The decision is grounded in policy, never in the document
being decided, so these two bodies of text must not be able to reach each
other. Two implementations of one seam, `PolicySource`:

  - `PolicyCorpus` loads a markdown file into memory and retrieves
    lexically. It needs no database and no embedding bill, which is what
    the M1 spike wanted and what the tests still want.
  - `RetrievedPolicy` goes through `hybrid_search(..., collection=policy)`,
    which is the built pipeline: pgvector plus FTS, fused with RRF, with
    the collection filter making the separation a database constraint
    rather than a convention.

Everything above this file takes a `PolicySource` and cannot tell the
difference, which is the point: swapping the corpus is configuration.
"""

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the to with".split()
)


@dataclass(frozen=True)
class PolicyClause:
    id: str
    """What a citation must name. A chunk id when the clause came from the
    database, a synthetic `clause-n` when it came from a markdown file."""
    ref: str
    """Human-readable reference, e.g. '4.2 Spend thresholds'."""
    text: str
    """The clause body, heading included, exactly as written."""
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    """Set when the clause came from retrieval, so a citation can be stored
    pointing at the row it quoted."""

    def cite_block(self) -> str:
        return f"[{self.id}] {self.ref}\n{self.text}"


class PolicySource(Protocol):
    """Anything that can hand back citable policy clauses for a query."""

    def retrieve(self, query: str, top_k: int = 8) -> list[PolicyClause]: ...


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


class RetrievedPolicy:
    """The built pipeline's policy source: hybrid retrieval, policy only.

    The `collection=policy` filter is not a convenience. It is the thing
    that stops an invoice from being cited as if it were policy, and it
    runs in the database rather than in a comment.

    A retrieved chunk is a chunk, not a clause, so `ref` is built from the
    filename and the chunk's position. When the policy corpus is chunked
    from markdown that reads close enough to a clause reference; when it
    is not, that is a chunking problem, and pretending otherwise in this
    file would only hide it.
    """

    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id

    def retrieve(self, query: str, top_k: int = 8) -> list[PolicyClause]:
        from app.db.models import Collection
        from app.retrieval.hybrid import hybrid_search

        chunks = hybrid_search(
            self.user_id, query, collection=Collection.policy, top_k=top_k
        )
        return [
            PolicyClause(
                id=str(chunk.id),
                ref=_clause_ref(chunk.filename, chunk.content, chunk.chunk_index),
                text=chunk.content,
                chunk_id=chunk.id,
                document_id=chunk.document_id,
            )
            for chunk in chunks
        ]


def _clause_ref(filename: str, content: str, chunk_index: int) -> str:
    """A reference a human can find in the source document.

    Prefers the first markdown heading in the chunk, because that is what
    the clause is actually called. Falls back to the chunk position, which
    is honest about being a position.
    """
    for line in content.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            return f"{filename}, {match.group(2).strip()}"
    return f"{filename}, part {chunk_index + 1}"
