"""The verbatim check: is this excerpt really in that source text?

One implementation, used by everything that claims a quote. The grounding
validator applies it to answer citations, extraction applies it to field
source spans, and the decision path applies it to policy excerpts. Same
discipline in all three places: a model may only claim what it can quote.

Matching is whitespace-normalized and case-insensitive, because a model
that re-wraps a line or lowercases a heading has not invented anything.
Nothing else is normalized: punctuation, digits and currency symbols must
match, since those are exactly the characters worth lying about.
"""


def normalize(text: str) -> str:
    """Collapse whitespace and case-fold, so re-wrapping is not a mismatch."""
    return " ".join(text.split()).lower()


def contains_verbatim(excerpt: str, source: str) -> bool:
    """True when `excerpt` appears in `source` under normalization.

    An empty excerpt is never verbatim: it quotes nothing, so it proves
    nothing, and returning True would let a blank span verify anything.
    """
    normalized = normalize(excerpt)
    if not normalized:
        return False
    return normalized in normalize(source)
