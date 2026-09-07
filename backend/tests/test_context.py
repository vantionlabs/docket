"""Contextual retrieval: what gets embedded is not what gets stored.

The bug this prevents is subtle. Prepending context to the STORED content
would corrupt every citation: the verbatim check would pass against text
the document never contained, which is the exact failure the whole
provenance story exists to stop.
"""

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
