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
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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


def _org_fk(*, nullable: bool = True) -> Mapped:
    """Tenant key (spec section 11).

    Required on Docket's own tables: nothing here can exist without a
    tenant. It stays nullable on the template's `source_documents` and
    `document_chunks`, because the template has no orgs and whether they
    gain them is the backport's decision, not this project's (section 14).
    """
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=nullable,
        index=True,
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


class Collection(enum.StrEnum):
    """Which body of text a document belongs to (spec section 8).

    Policy and transactional documents must never retrieve each other: a
    policy question that returns an invoice is wrong, and an invoice that
    quietly becomes policy is worse. Retrieval filters on this.
    """

    policy = "policy"
    transactional = "transactional"


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = _user_fk()
    org_id: Mapped[uuid.UUID | None] = _org_fk()
    collection: Mapped[Collection] = mapped_column(
        Enum(Collection, name="collection", native_enum=False, length=20),
        default=Collection.transactional,
        index=True,
    )
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
    org_id: Mapped[uuid.UUID | None] = _org_fk()
    collection: Mapped[Collection] = mapped_column(
        Enum(Collection, name="collection", native_enum=False, length=20),
        default=Collection.transactional,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )
    """Nullable since migration 0006. A chunk can exist before it has been
    embedded, and after an embedding-model change that invalidated the old
    vectors. Such a chunk is invisible to vector search and still found by
    FTS: degraded, not broken, and countable with scripts/reembed.py."""
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


# --- Docket domain (spec section 12) ------------------------------------
#
# `decisions` plus `decision_citations` plus `executions` is the audit
# trail. One join answers "why was this paid, on whose authority, citing
# what", which is the question an auditor asks a year later about the one
# invoice that turned out to be wrong.


class Role(enum.StrEnum):
    owner = "owner"
    reviewer = "reviewer"
    viewer = "viewer"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class Membership(Base):
    """Who may act in an org, and how far their authority runs.

    `approval_limit` is the amount this member may approve on their own
    (spec section 11). It is authority, not a preference, so it lives on
    the membership rather than on the user.
    """

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = _org_fk(nullable=False)
    user_id: Mapped[uuid.UUID] = _user_fk()
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="membership_role", native_enum=False, length=20), default=Role.viewer
    )
    approval_limit: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="memberships")


class Intake(Base):
    """How a document arrived. `external_ref` is the dedupe key: the same
    webhook delivered twice, or the same email pulled twice, is one intake."""

    __tablename__ = "intakes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = _org_fk(nullable=False)
    source: Mapped[str] = mapped_column(Text)  # webhook | schedule | upload | email
    external_ref: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Extraction(Base):
    """One extraction run over one document.

    `fields` is the typed model as JSON, spans included, so the detail
    screen can highlight a value's source text without re-running anything.
    `unverified_fields` is what rail 2 acts on.
    """

    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = _org_fk(nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    schema_name: Mapped[str] = mapped_column(Text)  # e.g. "invoice"
    document_text: Mapped[str] = mapped_column(Text, default="")
    """The parsed document this extraction was made from.

    Stored rather than re-derived, for two reasons. The detail screen
    highlights each field's source span inside it, and re-parsing a PDF on
    every page view would be both slow and not guaranteed to produce the
    same text. More importantly it makes the provenance claim reproducible:
    an auditor can re-run the verbatim check a year later against the exact
    text the check originally ran against.
    """
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    unverified_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    arithmetic_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    arithmetic_failures: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    model: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DecisionStatus(enum.StrEnum):
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    failed = "failed"


class Decision(Base):
    """The row the whole product is about.

    `outcome` is what the pipeline decided. `status` is where the case has
    got to. They are separate because a reviewer can approve a decision
    whose outcome was `reject`, and the disagreement is the point: the
    original stays, the override sits beside it, and the gap between them
    is measurable per rule (spec section 9).
    """

    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = _org_fk(nullable=False)
    user_id: Mapped[uuid.UUID] = _user_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True
    )

    outcome: Mapped[str] = mapped_column(Text)  # app.decisions.models.Outcome
    rationale: Mapped[str] = mapped_column(Text, default="")
    unmet_conditions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    rail_notes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    """Why the rails moved the outcome, in the reviewer's words. Not in the
    spec's column list; added because it is the first thing a reviewer needs
    to know and deriving it later would mean re-running the decision."""

    rule_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    grounding_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    grounding_failure: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[DecisionStatus] = mapped_column(
        Enum(DecisionStatus, name="decision_status", native_enum=False, length=20),
        default=DecisionStatus.pending_review,
        index=True,
    )
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    """A cost centre or role, never a person (spec section 9)."""

    decided_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reviewed_by: Mapped[uuid.UUID | None] = _user_fk(nullable=True, ondelete="SET NULL")
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    override_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    citations: Mapped[list["DecisionCitation"]] = relationship(
        back_populates="decision",
        cascade="all, delete-orphan",
        order_by="DecisionCitation.citation_index",
    )

    @property
    def effective_outcome(self) -> str:
        """What actually happened: the reviewer's call when they made one."""
        return self.override_outcome or self.outcome


class DecisionCitation(Base):
    """A policy clause that justified a decision, quoted verbatim.

    `chunk_id` is nullable because a decision can be grounded in an
    in-memory corpus (the spike, and tests) as well as a retrieved one.
    The excerpt and clause_ref are what an auditor reads either way.
    """

    __tablename__ = "decision_citations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL"), nullable=True
    )
    citation_index: Mapped[int] = mapped_column(Integer)  # 1-based [n] marker
    clause_ref: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)

    decision: Mapped[Decision] = relationship(back_populates="citations")


class Rule(Base):
    """The explicit gate of rail 3, per org.

    `auto_approve` defaults to false and stays false until the eval set
    says otherwise (spec section 13). A rule with `auto_approve` false is
    still useful: it names the approver.
    """

    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = _org_fk(nullable=False)
    name: Mapped[str] = mapped_column(Text)
    schema_name: Mapped[str] = mapped_column(Text, default="invoice")
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ExecutionStatus(enum.StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


class Execution(Base):
    """One outbound side effect, with the key that makes retrying it safe.

    The row is written BEFORE the outbound call (spec section 10). A retry
    that finds a completed row returns it and calls nothing, which is the
    difference between an at-least-once event engine and paying a supplier
    twice.
    """

    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = _org_fk(nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), index=True
    )
    adapter: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    request: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="execution_status", native_enum=False, length=20),
        default=ExecutionStatus.pending,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class PolicyObligation(Base):
    """One rule a policy clause imposes, indexed once at ingest.

    The index that makes retrieval auditable (spec section 8, extended).
    Without it, "we searched the policy and here is what came back" is the
    strongest claim the system can make. With it, the claim becomes "these
    rules applied and every one of them was considered", which is the one
    a client is actually buying.

    Rows are written by a model reading the policy, and are then data:
    readable, editable, and reviewable by the client whose policy it is. The
    model helps build the index. It does not decide at decision time whether
    a rule was relevant; that check runs in code against these rows.
    """

    __tablename__ = "policy_obligations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = _org_fk(nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dimension: Mapped[str] = mapped_column(Text, index=True)
    """app.decisions.coverage.Dimension. A closed set: a dimension the code
    cannot evaluate is one that cannot be checked."""
    schema_name: Mapped[str] = mapped_column(Text, default="invoice", index=True)
    """Which kind of document this rule governs.

    A policy corpus contains more than the one policy that applies. A travel
    and expenses policy has a threshold ladder too, and it governs expense
    claims; requiring its clauses when deciding a supplier invoice stuffs the
    evidence with rules that do not apply and makes the decision worse. Only
    a multi-document corpus reveals this, which is why it took one to find it.
    """
    in_force: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    """False for a superseded version retained for audit. The 2024 policy
    with the old thresholds is exactly the clause you least want pulled into
    a decision about a 2026 invoice."""
    applies_when: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    """Subject terms the document must mention for this rule to bear on it.
    Empty means it bears on every document of this kind.

    "Catering and hospitality commitments up to EUR 50,000 may be approved
    by a department head" is a real, in-force, invoice-governing `amount`
    rule that has nothing to say about a cleaning invoice. Without this it
    was required for every invoice, and the repair step pulled it into the
    evidence every time."""
    summary: Mapped[str] = mapped_column(Text)
    clause_ref: Mapped[str] = mapped_column(Text)
    always_applies: Mapped[bool] = mapped_column(Boolean, default=False)
    threshold: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
