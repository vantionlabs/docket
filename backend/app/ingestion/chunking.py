"""Chunking, in two shapes for two kinds of document.

`chunk_text` is token-aware: split on blank lines, pack paragraphs to about
`chunk_target_tokens`, and start each next chunk with the tail of the
previous one so answers spanning a boundary stay retrievable. Right for
prose, where a size target is the only structure available.

`chunk_by_heading` splits on headings instead, one chunk per section. Right
for a policy, where the document already carries the structure that matters
and packing to a size target throws it away. Five supplier entries at thirty
tokens each land in one 180-token chunk, and then: a query about one
supplier retrieves a chunk that is eighty percent other suppliers, the
chunk's `ref` names only its first heading so a citation of the fifth cannot
be resolved, and the obligations extracted from it are attributed to the
wrong clause.

Small chunks embed poorly on their own, which is the usual argument against
this. Contextual retrieval answers it: the text that gets embedded carries
the document name and heading path (app/ingestion/context.py), so a
fifteen-token clause is embedded with the context that makes it findable.
Without that, do not split this finely.
"""

import re
from dataclasses import dataclass

import tiktoken

from app.config import settings

_HEADING = re.compile(r"^#{1,6}\s+\S")

_enc = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    index: int
    content: str
    token_count: int
    source_start: int = -1
    """Character offset where this chunk's new content begins in the source.

    Carried rather than searched for later. Anything downstream that needs
    to know where a chunk came from used to locate it with
    `document.find(chunk.content[:200])`, which only works when the chunk
    text is a byte-exact substring of the source. It is not: paragraphs are
    split on blank lines and rejoined with exactly "\n\n", so a source with
    "\n\n\n" or trailing spaces (which is what docling emits from a PDF)
    produces chunks that appear nowhere in their own document. Every chunk
    then silently lost its heading path.
    """


def _tokens(text: str) -> int:
    return len(_enc.encode(text))


def _split_oversized(paragraph: str, target: int) -> list[str]:
    ids = _enc.encode(paragraph)
    return [_enc.decode(ids[i : i + target]) for i in range(0, len(ids), target)]


def _paragraphs_with_offsets(text: str) -> list[tuple[str, int]]:
    """Paragraphs and where each one starts in the source.

    Split on blank lines like the original, but keep the offset so a chunk
    can say where it came from instead of being searched for afterwards.
    """
    found: list[tuple[str, int]] = []
    cursor = 0
    for raw in text.split("\n\n"):
        stripped = raw.strip()
        if stripped:
            found.append((stripped, cursor + raw.index(stripped)))
        cursor += len(raw) + 2  # the separator we split on
    return found


def chunk_text(
    text: str,
    target_tokens: int | None = None,
    overlap_ratio: float | None = None,
) -> list[Chunk]:
    target = target_tokens or settings.chunk_target_tokens
    ratio = overlap_ratio if overlap_ratio is not None else settings.chunk_overlap_ratio
    overlap = int(target * ratio)

    paragraphs: list[tuple[str, int]] = []
    for para, offset in _paragraphs_with_offsets(text):
        if _tokens(para) > target:
            # A hard-split paragraph keeps the offset of its parent: every
            # piece came from there, and it is the heading path we want.
            paragraphs.extend((piece, offset) for piece in _split_oversized(para, target))
        else:
            paragraphs.append((para, offset))

    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    has_new_content = False  # guards against emitting an overlap-only chunk
    start = -1  # offset of the first NEW paragraph in the chunk being built

    def flush() -> None:
        nonlocal current, current_tokens, has_new_content, start
        if not current or not has_new_content:
            return
        content = "\n\n".join(current)
        chunks.append(
            Chunk(
                index=len(chunks),
                content=content,
                token_count=_tokens(content),
                source_start=start,
            )
        )
        has_new_content = False
        start = -1
        # Seed the next chunk with the tail of this one (overlap).
        if overlap > 0:
            ids = _enc.encode(content)
            tail = _enc.decode(ids[-overlap:]) if len(ids) > overlap else content
            current = [tail]
            current_tokens = _tokens(tail)
        else:
            current = []
            current_tokens = 0

    for para, offset in paragraphs:
        para_tokens = _tokens(para)
        if current_tokens + para_tokens > target and current:
            flush()
        if not has_new_content:
            # Where this chunk's own content starts, ignoring the overlap
            # tail carried over from the previous one.
            start = offset
        current.append(para)
        current_tokens += para_tokens
        has_new_content = True

    flush()
    return chunks


def chunk_by_heading(
    text: str,
    max_tokens: int | None = None,
) -> list[Chunk]:
    """One chunk per heading section, in document order.

    A section that runs past `max_tokens` is packed with `chunk_text`, so an
    unusually long clause degrades to size-based chunking rather than
    producing one enormous chunk. Text before the first heading becomes its
    own chunk: a document's preamble is often its scope statement, which is
    exactly the kind of rule that must stay retrievable.
    """
    limit = max_tokens or settings.chunk_target_tokens
    sections = _sections(text)
    chunks: list[Chunk] = []

    for content, offset in sections:
        if _tokens(content) <= limit:
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content=content,
                    token_count=_tokens(content),
                    source_start=offset,
                )
            )
            continue

        # Too long to keep whole. Fall back to size-based chunking within
        # this section, keeping every piece anchored to the section start so
        # the heading path still resolves.
        for piece in chunk_text(content, target_tokens=limit):
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content=piece.content,
                    token_count=piece.token_count,
                    source_start=offset + max(piece.source_start, 0),
                )
            )

    return chunks


def _sections(text: str) -> list[tuple[str, int]]:
    """Split at headings. Returns (section text, offset in the source)."""
    lines = text.splitlines(keepends=True)
    starts: list[int] = []
    cursor = 0
    for line in lines:
        if _HEADING.match(line.strip()):
            starts.append(cursor)
        cursor += len(line)

    if not starts:
        stripped = text.strip()
        return [(stripped, text.index(stripped))] if stripped else []

    # Anything before the first heading is its own section.
    bounds = ([0] if starts[0] > 0 else []) + starts
    sections: list[tuple[str, int]] = []
    for i, start in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else len(text)
        raw = text[start:end]
        stripped = raw.strip()
        if stripped:
            sections.append((stripped, start + raw.index(stripped)))
    return sections
