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

from app.logging import get_logger

log = get_logger(__name__)

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
    """Anything that can hand back citable policy clauses.

    `retrieve` is ranking: what is most relevant to this query. `by_chunk_ids`
    is lookup: these specific clauses, because something else determined they
    are required. Coverage repair needs the second, and a source that could
    only rank would have no way to add a clause it failed to rank.
    """

    def retrieve(self, query: str, top_k: int = 8) -> list[PolicyClause]: ...

    def by_chunk_ids(self, chunk_ids: list) -> list[PolicyClause]: ...


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

    def by_chunk_ids(self, chunk_ids: list) -> list[PolicyClause]:
        """Look up by id. The in-memory corpus has no chunks, so its own
        `clause-n` ids are what a caller can hold."""
        wanted = {str(cid) for cid in chunk_ids}
        return [clause for clause in self.clauses if clause.id in wanted]

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

    def by_chunk_ids(self, chunk_ids: list) -> list[PolicyClause]:
        """Fetch specific policy chunks, bypassing ranking entirely.

        Still filtered on user and collection: a required clause is not a
        reason to reach outside the policy corpus or another tenant's rows.
        """
        if not chunk_ids:
            return []

        from sqlalchemy import select

        from app.db.engine import SessionLocal
        from app.db.models import Collection, DocumentChunk, SourceDocument

        with SessionLocal() as db:
            rows = db.execute(
                select(
                    DocumentChunk.id,
                    DocumentChunk.document_id,
                    DocumentChunk.chunk_index,
                    DocumentChunk.content,
                    SourceDocument.filename,
                )
                .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
                .where(
                    DocumentChunk.id.in_(chunk_ids),
                    DocumentChunk.user_id == self.user_id,
                    DocumentChunk.collection == Collection.policy,
                )
            ).all()

        return [
            PolicyClause(
                id=str(row.id),
                ref=_clause_ref(row.filename, row.content, row.chunk_index),
                text=row.content,
                chunk_id=row.id,
                document_id=row.document_id,
            )
            for row in rows
        ]

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


class CoveredPolicy:
    """Retrieval that cannot silently miss a rule that applies.

    Wraps any `PolicySource`. Ranking finds what is most relevant; this adds
    what is *required*, by looking up the obligations the document triggers
    and pulling in any whose clause ranking did not return.

    The important part is that a gap is repaired rather than reported. A
    warning that a clause was missed is only useful to whoever reads logs; a
    decision made without a rule that applies is wrong no matter who reads
    what afterwards. So the missing clauses are fetched directly by id and
    added to the evidence before the model sees anything, and the decision
    is made on the complete set.

    Only a gap that cannot be repaired reaches the rails: an obligation
    whose clause has been deleted, or was never chunked. That is rare, and
    it is a real reason to stop and ask a person.
    """

    def __init__(self, inner: PolicySource, obligations: list, triggered: set) -> None:
        self.inner = inner
        self.obligations = obligations
        self.triggered = triggered
        self.report = None

    def retrieve(self, query: str, top_k: int = 8) -> list[PolicyClause]:
        from app.decisions.coverage import check_coverage

        clauses = list(self.inner.retrieve(query, top_k=top_k))
        found = {clause.id for clause in clauses}

        report = check_coverage(self.obligations, self.triggered, found)
        gaps_before = list(report.missed)

        if gaps_before:
            repaired = self._fetch(gaps_before)
            clauses.extend(repaired)
            # Re-check against the repaired set so `report.missed` ends up
            # holding only what could NOT be repaired. Anything else would
            # escalate cases the system just fixed.
            report = check_coverage(
                self.obligations, self.triggered, found | {c.id for c in repaired}
            )
            log.info(
                "coverage.repaired",
                pulled_in=sorted({o.clause_ref for o in gaps_before if o not in report.missed}),
                ranked=len(found),
                added=len(repaired),
            )

        if report.missed:
            # This one IS a problem: a rule that applies, whose clause could
            # not be fetched at all. Rail 1b turns it into needs_human.
            log.warning(
                "coverage.unrepairable",
                missed=sorted({o.clause_ref for o in report.missed}),
                recall=round(report.recall, 3),
            )

        self.report = report
        return clauses

    def _fetch(self, missed: list) -> list[PolicyClause]:
        """Pull missed obligations' clauses straight from their rows.

        Keyed by `clause_key`, the same identifier the coverage check
        matched on. Using a different one here would report gaps that
        repair then fails to fill, without either half being wrong on its
        own."""
        keys = [o.clause_key for o in missed]
        return self.inner.by_chunk_ids(keys) if keys else []
