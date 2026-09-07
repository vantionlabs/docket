"""index policy clauses as obligations, so coverage can be proved

Top-k retrieval fails in two ways and only one of them is visible. An
irrelevant result gets caught by the verbatim check, the judge, or a human.
A relevant result that was never returned is caught by nothing: the
decision comes back confident, correctly cited, and silent about the rule
nobody asked. The M1 spike hit exactly this with a USD invoice and the
currency clause.

This table is the fix. Each policy clause is indexed once into the
obligations it imposes, so a decision can compute which rules apply in code
and then assert every one of them was actually retrieved.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

DIMENSIONS = (
    "'amount','purchase_order','supplier','currency','vat',"
    "'payment_terms','duplicate','scope','escalation'"
)


def upgrade() -> None:
    op.create_table(
        "policy_obligations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("clause_ref", sa.Text(), nullable=False),
        sa.Column("always_applies", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("threshold", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            f"dimension IN ({DIMENSIONS})", name="ck_policy_obligations_dimension"
        ),
    )
    op.create_index("ix_policy_obligations_org", "policy_obligations", ["org_id"])
    op.create_index("ix_policy_obligations_document", "policy_obligations", ["document_id"])
    op.create_index("ix_policy_obligations_chunk", "policy_obligations", ["chunk_id"])
    # The coverage check reads every obligation for an org and filters by
    # dimension in code, so this is the index that serves it.
    op.create_index(
        "ix_policy_obligations_org_dimension", "policy_obligations", ["org_id", "dimension"]
    )


def downgrade() -> None:
    op.drop_table("policy_obligations")
