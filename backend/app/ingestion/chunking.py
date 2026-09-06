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


def _tokens(text: str) -> int:
    return len(_enc.encode(text))


def _split_oversized(paragraph: str, target: int) -> list[str]:
    ids = _enc.encode(paragraph)
    return [_enc.decode(ids[i : i + target]) for i in range(0, len(ids), target)]


def chunk_text(
    text: str,
    target_tokens: int | None = None,
    overlap_ratio: float | None = None,
) -> list[Chunk]:
    target = target_tokens or settings.chunk_target_tokens
    ratio = overlap_ratio if overlap_ratio is not None else settings.chunk_overlap_ratio
    overlap = int(target * ratio)

    paragraphs: list[str] = []
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if _tokens(para) > target:
            paragraphs.extend(_split_oversized(para, target))
        else:
            paragraphs.append(para)

    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    has_new_content = False  # guards against emitting an overlap-only chunk

    def flush() -> None:
        nonlocal current, current_tokens, has_new_content
        if not current or not has_new_content:
            return
        content = "\n\n".join(current)
        chunks.append(Chunk(index=len(chunks), content=content, token_count=_tokens(content)))
        has_new_content = False
        # Seed the next chunk with the tail of this one (overlap).
        if overlap > 0:
            ids = _enc.encode(content)
            tail = _enc.decode(ids[-overlap:]) if len(ids) > overlap else content
            current = [tail]
            current_tokens = _tokens(tail)
        else:
            current = []
            current_tokens = 0

    for para in paragraphs:
        para_tokens = _tokens(para)
        if current_tokens + para_tokens > target and current:
            flush()
        current.append(para)
        current_tokens += para_tokens
        has_new_content = True

    flush()
    return chunks
