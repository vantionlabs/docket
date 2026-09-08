"""Contextual retrieval: what gets embedded is not what gets stored.

The bug this prevents is subtle. Prepending context to the STORED content
would corrupt every citation: the verbatim check would pass against text
the document never contained, which is the exact failure the whole
provenance story exists to stop.
"""

import pytest

from app.ingestion.context import contextualize, heading_path

POLICY = """# Northwind BV procurement policy

Preamble.

## 2. Purchase orders

Every purchase above EUR 500 requires a purchase order.

### 2.1 Exceptions

This does not apply to intercompany recharges.
"""

ORPHAN = "This does not apply to intercompany recharges."


def test_a_chunk_gets_its_heading_path_back():
    """The chunk that motivates the whole technique: alone it is about
    nothing, and no query for 'purchase order' will find it."""
    assert heading_path(POLICY, ORPHAN) == [
        "Northwind BV procurement policy",
        "2. Purchase orders",
        "2.1 Exceptions",
    ]


def test_the_embedded_text_carries_the_context():
    embedded = contextualize(ORPHAN, "policy.md", POLICY, strategy="structural")
    assert "2. Purchase orders" in embedded
    assert "policy.md" in embedded
    assert embedded.endswith(ORPHAN)


def test_the_original_text_is_never_altered():
    """Only the embedded copy is contextualized. If the stored content
    changed, every citation quoting it would be quoting something the
    document does not say."""
    embedded = contextualize(ORPHAN, "policy.md", POLICY, strategy="structural")
    assert ORPHAN in embedded
    assert embedded != ORPHAN  # context was added to the embedded copy
    # And the source document is untouched by the call.
    assert ORPHAN in POLICY


def test_off_returns_the_chunk_unchanged():
    assert contextualize(ORPHAN, "policy.md", POLICY, strategy="off") == ORPHAN


def test_a_chunk_that_cannot_be_located_claims_no_context():
    """A chunk we cannot place is one we should not invent a heading for."""
    assert heading_path(POLICY, "text from a different document entirely") == []


def test_a_deeper_heading_closes_the_shallower_ones_below_it():
    """Walking headings must not accumulate siblings: section 3 is not
    inside section 2."""
    doc = "## 2. POs\n\nA.\n\n### 2.1 Detail\n\nB.\n\n## 3. Currency\n\nPayable in euro.\n"
    assert heading_path(doc, "Payable in euro.") == ["3. Currency"]


# --- chunks carry where they came from ----------------------------------

MESSY = (
    "# Northwind policy\n\nIntro.\n\n\n"
    "## 2. Purchase orders   \n\nEvery purchase above EUR 500 requires a PO.\n\n\n\n"
    "### 2.1 Exceptions\n\nThis does not apply to intercompany recharges.\n\n\n"
    "## 3. Currency\n\nInvoices are payable in euro.\n"
)


def test_a_chunk_knows_where_it_started():
    from app.ingestion.chunking import chunk_text

    for chunk in chunk_text(MESSY, target_tokens=30):
        assert chunk.source_start >= 0, f"chunk {chunk.index} has no source offset"


def test_varied_spacing_no_longer_loses_every_heading_path():
    """The bug: paragraphs are rejoined with exactly "\\n\\n", so a source
    containing "\\n\\n\\n" or trailing spaces produces chunks that appear
    nowhere in their own document. `document.find(...)` then failed for
    every chunk and each silently fell back to filename-only context.

    docling emits exactly that spacing from a PDF, so this failed totally on
    real client documents while looking perfect on hand-written markdown.
    """
    from app.ingestion.chunking import chunk_text

    chunks = chunk_text(MESSY, target_tokens=30)
    non_first = [c for c in chunks if c.index > 0]
    assert non_first, "need more than one chunk to test this"

    by_search = [c for c in non_first if not heading_path(MESSY, c.content)]
    by_offset = [
        c for c in non_first if not heading_path(MESSY, c.content, c.source_start)
    ]
    assert by_search, "the old search path should still fail on this document"
    assert not by_offset, "the offset path must place every chunk"


def test_the_first_chunk_legitimately_has_no_path():
    """Not a failure. There are no headings above a document's own title,
    and filename-only is the right context for that chunk."""
    from app.ingestion.chunking import chunk_text

    first = chunk_text(MESSY, target_tokens=30)[0]
    assert heading_path(MESSY, first.content, first.source_start) == []


def test_the_clean_corpus_places_every_non_first_chunk():
    from pathlib import Path

    from app.ingestion.chunking import chunk_text

    corpus = Path(__file__).resolve().parents[1] / "evals/fixtures/corpus"
    if not corpus.exists():
        pytest.skip("corpus not generated")

    lost = 0
    for path in sorted(corpus.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for chunk in chunk_text(text, target_tokens=180):
            if chunk.index and not heading_path(text, chunk.content, chunk.source_start):
                lost += 1
    assert lost == 0


def test_contextualize_uses_the_offset_when_given_one():
    embedded = contextualize(
        "This does not apply to intercompany recharges.",
        "policy.md",
        MESSY,
        strategy="structural",
        source_start=MESSY.index("This does not apply"),
    )
    assert "2.1 Exceptions" in embedded
