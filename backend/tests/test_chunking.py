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


# --- chunking a policy by its own structure -----------------------------

POLICY = """# Approved supplier list

Maintained by Procurement.

## 1. Contoso Cleaning Services BV

Approved for facilities. Standard 30 day terms.

## 2. Fabrikam Office Supplies BV

Approved for office consumables. Standard 30 day terms.

## 3. Northwind IT Partners BV

Approved for IT hardware. Standard 30 day terms.
"""


def test_each_heading_becomes_its_own_chunk():
    """The bug this fixes: at a 180-token target, five thirty-token supplier
    entries share one chunk. A query about one retrieves four others, the
    chunk's ref names only the first, and obligations extracted from it are
    attributed to the wrong clause."""
    from app.ingestion.chunking import chunk_by_heading

    chunks = chunk_by_heading(POLICY, max_tokens=180)
    assert len(chunks) == 4  # preamble + three suppliers
    assert "Contoso" in chunks[1].content
    assert "Fabrikam" not in chunks[1].content


def test_size_chunking_would_have_merged_them():
    """The comparison that motivates the change."""
    from app.ingestion.chunking import chunk_by_heading, chunk_text

    assert len(chunk_text(POLICY, target_tokens=180)) < len(
        chunk_by_heading(POLICY, max_tokens=180)
    )


def test_the_preamble_survives_as_its_own_chunk():
    """Text before the first heading is often the scope statement, which is
    exactly the kind of rule that has to stay retrievable."""
    from app.ingestion.chunking import chunk_by_heading

    assert "Maintained by Procurement" in chunk_by_heading(POLICY, 180)[0].content


def test_an_oversized_section_falls_back_to_size_chunking():
    """One enormous clause should degrade to the old behaviour, not produce
    a single chunk nothing can retrieve from."""
    from app.ingestion.chunking import chunk_by_heading

    long_section = "## 1. A long clause\n\n" + "\n\n".join(
        f"Paragraph {i} with enough words in it to take up real tokens." for i in range(60)
    )
    chunks = chunk_by_heading(long_section, max_tokens=100)
    assert len(chunks) > 1
    assert all(c.token_count <= 200 for c in chunks)


def test_every_chunk_still_knows_where_it_started():
    from app.ingestion.chunking import chunk_by_heading
    from app.ingestion.context import heading_path

    for chunk in chunk_by_heading(POLICY, 180):
        assert chunk.source_start >= 0
        if chunk.index:
            assert heading_path(POLICY, chunk.content, chunk.source_start)


def test_a_document_with_no_headings_is_one_chunk():
    from app.ingestion.chunking import chunk_by_heading

    chunks = chunk_by_heading("Just some prose with no headings at all.", 180)
    assert len(chunks) == 1
