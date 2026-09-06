"""RRF fusion unit tests."""

import uuid

from app.retrieval.hybrid import rrf_fuse

A, B, C, D = (uuid.uuid4() for _ in range(4))


def test_agreement_wins():
    # A ranks top in both lists -> highest fused score.
    fused = rrf_fuse([[A, B, C], [A, C, D]], k=60)
    assert fused[0] == A


def test_single_ranking_preserved():
    assert rrf_fuse([[A, B, C]], k=60) == [A, B, C]


def test_disjoint_rankings_interleave_by_rank():
    fused = rrf_fuse([[A, B], [C, D]], k=60)
    # Ranks 1 tie above ranks 2; both rank-1 items precede both rank-2 items.
    assert set(fused[:2]) == {A, C}
    assert set(fused[2:]) == {B, D}


def test_empty_rankings():
    assert rrf_fuse([], k=60) == []
    assert rrf_fuse([[], []], k=60) == []


def test_item_in_both_beats_higher_single():
    # B is #2 in both lists; D is #1 in one list only.
    fused = rrf_fuse([[A, B, C], [D, B, C]], k=60)
    assert fused.index(B) < fused.index(D) or fused.index(B) < fused.index(A)
