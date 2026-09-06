"""SQLAlchemy models — the app-owned schema.

Auth lives in this backend (fastapi-users). Alembic owns the entire schema,
including the `users` table — one migration system, one database. User ids
are UUIDs; every user-scoped table FKs to `users.id`.

The `User` model is the fastapi-users table extended with our fields. All
user management (register, login, password hashing, reset) runs through
fastapi-users against this table; the rest of the app just reads
`users.id` as a foreign key.
"""

import enum
import uuid
from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSONB, datetime: DateTime(timezone=True)}


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _user_fk(*, nullable: bool = False, ondelete: str = "CASCADE") -> Mapped:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete=ondelete),
        nullable=nullable,
    )


class User(SQLAlchemyBaseUserTableUUID, Base):
    """The fastapi-users user table. The mixin provides `id` (UUID), `email`,
    `hashed_password`, `is_active`, `is_superuser`, `is_verified`. We name
    the table `users` (plural; also sidesteps quoting the reserved word
    `user`) and add `created_at`."""

    __tablename__ = "users"

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ApiKey(Base):
    """A hashed API key for non-browser clients (service-to-service, headless,
    widgets). We store only the SHA-256 hash + a display prefix; the plaintext
    is shown once at creation."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(Text)
    key_hash: Mapped[str] = mapped_column(Text, unique=True, index=True)
    prefix: Mapped[str] = mapped_column(Text)  # e.g. "sk_a1b2c3" for display
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LlmUsage(Base):
    """One row per model call: tokens + computed cost, for spend visibility
    and per-user limits/billing."""

    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, ondelete="SET NULL")
    operation: Mapped[str] = mapped_column(Text)  # chat | embedding | grounding
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DocumentStatus(enum.StrEnum):
    pending_upload = "pending_upload"
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = _user_fk()
    filename: Mapped[str] = mapped_column(Text)
    r2_key: Mapped[str] = mapped_column(Text, unique=True)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=False, length=20),
        default=DocumentStatus.pending_upload,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = _user_fk()
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimensions))
    # `fts` is a GENERATED tsvector column added in the initial migration
    # (SQLAlchemy can't declare generated tsvector portably; it exists in
    # the database and is queried with text() in retrieval).

    document: Mapped[SourceDocument] = relationship(back_populates="chunks")


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str] = mapped_column(Text, default="New chat")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="ChatMessage.sequence"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("thread_id", "sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    thread: Mapped[ChatThread] = relationship(back_populates="messages")
    citations: Mapped[list["MessageCitation"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageCitation.citation_index",
    )


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE")
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    citation_index: Mapped[int] = mapped_column(Integer)  # 1-based [n] marker
    excerpt: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text, default="")  # denormalized for display

    message: Mapped[ChatMessage] = relationship(back_populates="citations")


class EventStatus(enum.StrEnum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class Event(Base):
    """Event-driven intake (Launchpad pattern): every background job is an
    event row processed by a Celery worker running the workflow registered
    for its type. The row doubles as the job's audit trail."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, ondelete="SET NULL")
    type: Mapped[str] = mapped_column(Text)  # e.g. "document.ingest"
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status", native_enum=False, length=20),
        default=EventStatus.queued,
    )
    # Dedupe key: a re-delivered webhook / retried request with the same key
    # returns the existing event instead of processing twice.
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    # Retry accounting. `attempts` increments on each processing try; when it
    # reaches `max_attempts` a failing event is dead-lettered (status=failed).
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
