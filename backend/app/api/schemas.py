"""Pydantic request/response schemas for the API surface."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """FastAPI's default error body: `{"detail": "..."}`."""

    detail: str


# Reusable OpenAPI `responses` blocks for documented error cases.
UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Not authenticated"}}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Not found or not yours"}}


# --- events ---
class EventIn(BaseModel):
    type: str = Field(description="Registered event type, e.g. `document.ingest`.")
    payload: dict = Field(default_factory=dict, description="Arbitrary JSON for the workflow.")


class EventOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str = Field(description="`queued` | `processing` | `done` | `failed` (dead-letter).")
    attempts: int = Field(description="Processing attempts so far.")
    max_attempts: int = Field(description="Attempts before dead-lettering.")
    result: dict | None = Field(default=None, description="Workflow output when `done`.")
    error: str | None = None
    created_at: datetime


# --- documents ---
class PresignRequest(BaseModel):
    filename: str = Field(description="Original file name.")
    content_type: str = Field(
        description="MIME type. The browser PUT must send this exact value.",
        examples=["text/markdown", "application/pdf"],
    )
    size_bytes: int | None = Field(default=None, description="File size, for display.")


class PresignResponse(BaseModel):
    document_id: uuid.UUID
    key: str = Field(description="The object key in the R2 bucket.")
    upload_url: str = Field(description="Presigned PUT URL, short-lived.")


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int | None
    status: str = Field(
        description="`pending_upload` | `uploaded` | `processing` | `ready` | `failed`."
    )
    error: str | None = Field(default=None, description="Set when `status` is `failed`.")
    created_at: datetime


# --- threads / messages ---
class ThreadOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class CitationOut(BaseModel):
    id: uuid.UUID
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    citation_index: int
    excerpt: str
    filename: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sequence: int
    created_at: datetime
    citations: list[CitationOut] = Field(default_factory=list)


# --- decisions (Docket) ---
class DecisionCitationOut(BaseModel):
    id: uuid.UUID
    citation_index: int = Field(description="1-based, matching an `[n]` marker in the rationale.")
    clause_ref: str = Field(description="Where in the policy this came from.")
    excerpt: str = Field(description="Verbatim text from that clause.")
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


class ExtractedFieldOut(BaseModel):
    name: str
    value: str | None
    source_span: str | None = Field(
        default=None, description="The verbatim text this value was read from."
    )
    verified: bool = Field(description="False when the span was not found in the document.")


class DecisionOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    extraction_id: uuid.UUID | None
    outcome: str = Field(
        description="`auto_approve` | `route_for_approval` | `reject` | `needs_human`."
    )
    effective_outcome: str = Field(
        description="The reviewer's call when they overrode, otherwise `outcome`."
    )
    rationale: str
    unmet_conditions: list[str]
    rail_notes: list[str] = Field(
        description="Why the rails moved the outcome. The first thing a reviewer needs."
    )
    rule_id: str | None = Field(default=None, description="The rule that authorised auto-approve.")
    grounding_passed: bool
    grounding_failure: str | None = None
    status: str = Field(
        description="`pending_review` | `approved` | `rejected` | `executed` | `failed`."
    )
    assigned_to: str | None = Field(default=None, description="A cost centre or role.")
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    override_outcome: str | None = None
    override_note: str | None = None
    created_at: datetime
    citations: list[DecisionCitationOut] = Field(default_factory=list)


class DecisionDetailOut(DecisionOut):
    """The decision detail screen's payload (spec section 15)."""

    filename: str
    unverified_fields: list[str] = Field(default_factory=list)
    arithmetic_ok: bool = True
    arithmetic_failures: list[str] = Field(default_factory=list)
    fields: list[ExtractedFieldOut] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    override_outcome: str | None = Field(
        default=None,
        description=(
            "Set when the reviewer disagrees with the pipeline. The original "
            "`outcome` is kept, so the disagreement stays measurable."
        ),
    )
    note: str | None = Field(default=None, description="Why, for the audit trail.")


class RejectRequest(BaseModel):
    note: str | None = Field(default=None, description="Why, for the audit trail.")


class ApprovalResponse(BaseModel):
    decision_id: uuid.UUID
    status: str
    event_id: uuid.UUID | None = Field(
        default=None, description="The `decision.execute` event, when one was emitted."
    )
