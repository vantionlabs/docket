"""Token-aware chunking: paragraph-preserving, fixed target with overlap.

Splits on blank lines (paragraphs), packs paragraphs into chunks of about
`chunk_target_tokens`, and starts each next chunk with the tail of the
previous one (overlap) so answers spanning a boundary stay retrievable.
Oversized single paragraphs are hard-split on token windows.
"""

from dataclasses import dataclass

import tiktoken

from app.config import settings

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
