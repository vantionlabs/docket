"""Chunking unit tests (fast lane; tiktoken runs offline)."""

from app.ingestion.chunking import chunk_text


def test_short_text_single_chunk():
    chunks = chunk_text("Hello world.", target_tokens=100, overlap_ratio=0.1)
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].content == "Hello world."


def test_empty_text_no_chunks():
    assert chunk_text("", target_tokens=100) == []
    assert chunk_text("\n\n\n", target_tokens=100) == []


def test_long_text_splits_with_sequential_indices():
    paragraphs = [f"Paragraph {i}. " + ("word " * 120) for i in range(6)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, target_tokens=200, overlap_ratio=0.1)
    assert len(chunks) > 1
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_overlap_seeds_next_chunk():
    paragraphs = [f"Unique-{i} " + ("filler " * 150) for i in range(4)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, target_tokens=200, overlap_ratio=0.2)
    assert len(chunks) >= 2
    # The tail of chunk 0 must reappear at the head of chunk 1.
    tail = chunks[0].content[-40:]
    assert tail.strip()[:20] in chunks[1].content


def test_no_overlap_only_final_chunk_duplicate():
    """Regression: the final flush must not emit an overlap-only chunk."""
    paragraphs = ["alpha " * 100, "beta " * 100]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, target_tokens=120, overlap_ratio=0.2)
    # No chunk may consist solely of the previous chunk's tail.
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        assert cur.content != prev.content
        assert len(cur.content) > 0


def test_oversized_single_paragraph_hard_splits():
    text = "token " * 1000  # one giant paragraph, no blank lines
    chunks = chunk_text(text, target_tokens=200, overlap_ratio=0)
    assert len(chunks) > 1
    assert all(c.token_count <= 220 for c in chunks)  # small tolerance
