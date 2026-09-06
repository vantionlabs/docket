"""docket domain: orgs, intakes, extractions, decisions, rules, executions

Adds `collection` and `org_id` to the template's document tables (spec
section 8 and 11), then everything the decision pipeline needs.

`org_id` is nullable here. M3 wires orgs into the auth seam and backfills;
creating the columns now means the tables are never rewritten under live
data, and a nullable column is honest about the fact that nothing sets it
yet.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

COLLECTIONS = "('policy','transactional')"


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("approval_limit", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "user_id", name="uq_memberships_org_user"),
        sa.CheckConstraint("role IN ('owner','reviewer','viewer')", name="ck_memberships_role"),
    )
    op.create_index("ix_memberships_org", "memberships", ["org_id"])
    op.create_index("ix_memberships_user", "memberships", ["user_id"])

    # --- the template's tables gain a tenant and a collection ---
    for table in ("source_documents", "document_chunks"):
        op.add_column(
            table,
            sa.Column(
                "org_id",
                UUID(as_uuid=True),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "collection",
                sa.String(20),
                nullable=False,
                server_default="transactional",
            ),
        )
        op.create_check_constraint(
            f"ck_{table}_collection", table, f"collection IN {COLLECTIONS}"
        )
        op.create_index(f"ix_{table}_org", table, ["org_id"])

    # Retrieval always filters user + collection together, so index the pair.
    op.create_index(
        "ix_document_chunks_user_collection", "document_chunks", ["user_id", "collection"]
    )

    op.create_table(
        "intakes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=True, unique=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw", JSONB(), nullable=True),
    )
    op.create_index("ix_intakes_document", "intakes", ["document_id"])
    op.create_index("ix_intakes_org", "intakes", ["org_id"])

    op.create_table(
        "extractions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("fields", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "unverified_fields",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("arithmetic_ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "arithmetic_failures",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_extractions_document", "extractions", ["document_id"])
    op.create_index("ix_extractions_org", "extractions", ["org_id"])

    op.create_table(
        "decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "extraction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("extractions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "unmet_conditions", sa.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("rail_notes", sa.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("rule_id", sa.Text(), nullable=True),
        sa.Column("grounding_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("grounding_failure", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_review"),
        sa.Column("assigned_to", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "reviewed_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("override_outcome", sa.Text(), nullable=True),
        sa.Column("override_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "outcome IN ('auto_approve','route_for_approval','reject','needs_human')",
            name="ck_decisions_outcome",
        ),
        sa.CheckConstraint(
            "override_outcome IS NULL OR override_outcome IN "
            "('auto_approve','route_for_approval','reject','needs_human')",
            name="ck_decisions_override_outcome",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review','approved','rejected','executed','failed')",
            name="ck_decisions_status",
        ),
    )
    op.create_index("ix_decisions_document", "decisions", ["document_id"])
    op.create_index("ix_decisions_org", "decisions", ["org_id"])
    op.create_index("ix_decisions_status", "decisions", ["status"])
    # The queue reads pending decisions oldest first (spec section 15).
    op.create_index("ix_decisions_queue", "decisions", ["status", "created_at"])

    op.create_table(
        "decision_citations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "decision_id",
            UUID(as_uuid=True),
            sa.ForeignKey("decisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("clause_ref", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
    )
    op.create_index("ix_decision_citations_decision", "decision_citations", ["decision_id"])

    op.create_table(
        "rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("schema_name", sa.Text(), nullable=False, server_default="invoice"),
        sa.Column("conditions", JSONB(), nullable=False, server_default="{}"),
        # Auto-approve stays off until the eval set says otherwise (section 13).
        sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_rules_org", "rules", ["org_id"])

    op.create_table(
        "executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "decision_id",
            UUID(as_uuid=True),
            sa.ForeignKey("decisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("adapter", sa.Text(), nullable=False),
        # The unique constraint is the idempotency guarantee, not the code
        # around it: two concurrent retries cannot both insert this key.
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("request", JSONB(), nullable=True),
        sa.Column("response", JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','failed')", name="ck_executions_status"
        ),
    )
    op.create_index("ix_executions_decision", "executions", ["decision_id"])
    op.create_index("ix_executions_org", "executions", ["org_id"])


def downgrade() -> None:
    op.drop_table("executions")
    op.drop_table("rules")
    op.drop_table("decision_citations")
    op.drop_table("decisions")
    op.drop_table("extractions")
    op.drop_table("intakes")
    op.drop_index("ix_document_chunks_user_collection", table_name="document_chunks")
    for table in ("source_documents", "document_chunks"):
        op.drop_index(f"ix_{table}_org", table_name=table)
        op.drop_constraint(f"ck_{table}_collection", table, type_="check")
        op.drop_column(table, "collection")
        op.drop_column(table, "org_id")
    op.drop_table("memberships")
    op.drop_table("organizations")
