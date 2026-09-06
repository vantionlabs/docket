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
