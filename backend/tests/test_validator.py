"""Structural grounding checks (no LLM judge — that path is integration)."""

import uuid
from unittest.mock import patch

from app.agent.output import AgentCitation, GroundedAnswer
from app.grounding.turn_registry import TurnRegistry
from app.grounding.validator import validate
from app.retrieval.hybrid import RetrievedChunk


def make_registry(
    content: str = "The revenue grew by 12 percent in 2025.",
) -> tuple[TurnRegistry, RetrievedChunk]:
    chunk = RetrievedChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        content=content,
        filename="report.md",
    )
    registry = TurnRegistry()
    registry.record([chunk])
    return registry, chunk


def test_insufficient_evidence_passes_without_citations():
    registry, _ = make_registry()
    answer = GroundedAnswer(answer="", citations=[], insufficient_evidence=True)
    result = validate(answer, registry)
    assert result.ok and result.citations == []


def test_marker_without_citation_fails():
    registry, _ = make_registry()
    answer = GroundedAnswer(answer="Revenue grew [1].", citations=[])
    result = validate(answer, registry)
    assert not result.ok
    assert "markers without citations" in result.reason


def test_unretrieved_chunk_fails():
    registry, _ = make_registry()
    answer = GroundedAnswer(
        answer="Revenue grew [1].",
        citations=[AgentCitation(index=1, chunk_id=str(uuid.uuid4()), excerpt="revenue grew")],
    )
    result = validate(answer, registry)
    assert not result.ok
    assert "unretrieved" in result.reason


def test_excerpt_not_in_chunk_fails():
    registry, chunk = make_registry()
    answer = GroundedAnswer(
        answer="Revenue grew [1].",
        citations=[AgentCitation(index=1, chunk_id=str(chunk.id), excerpt="profits doubled")],
    )
    result = validate(answer, registry)
    assert not result.ok
    assert "excerpt not found" in result.reason


def test_valid_citation_passes_structural_checks():
    registry, chunk = make_registry()
    answer = GroundedAnswer(
        answer="Revenue grew by 12 percent [1].",
        citations=[
            AgentCitation(
                index=1, chunk_id=str(chunk.id), excerpt="revenue grew by 12 percent"
            )
        ],
    )
    with patch("app.grounding.validator._judge", return_value=[]):
        result = validate(answer, registry)
    assert result.ok
    assert result.citations is not None and len(result.citations) == 1
    assert result.citations[0].filename == "report.md"


def test_judge_rejection_fails_closed():
    registry, chunk = make_registry()
    answer = GroundedAnswer(
        answer="Revenue grew by 12 percent [1].",
        citations=[
            AgentCitation(
                index=1, chunk_id=str(chunk.id), excerpt="revenue grew by 12 percent"
            )
        ],
    )
    with patch("app.grounding.validator._judge", return_value=[1]):
        result = validate(answer, registry)
    assert not result.ok
    assert "judge rejected" in result.reason


def test_unreferenced_citations_are_pruned():
    registry, chunk = make_registry()
    answer = GroundedAnswer(
        answer="Revenue grew by 12 percent [1].",
        citations=[
            AgentCitation(index=1, chunk_id=str(chunk.id), excerpt="revenue grew by 12 percent"),
            AgentCitation(index=2, chunk_id=str(chunk.id), excerpt="in 2025"),  # no [2] marker
        ],
    )
    with patch("app.grounding.validator._judge", return_value=[]):
        result = validate(answer, registry)
    assert result.ok
    assert result.citations is not None and len(result.citations) == 1
