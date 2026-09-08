"""obligations know what they govern and whether they are in force

A policy corpus is not one policy. It has a travel and expenses policy with
its own threshold ladder, a capex approval matrix shaped like the
procurement one, and a superseded version of the procurement policy carrying
last year's limits. All of them produce perfectly real obligations.

Coverage checking required every one of them for every decision, so a
supplier invoice was being checked against expense-claim thresholds and
2024 spend limits, and the repair step dutifully fetched those clauses into
the evidence. It made decisions worse, and a single-document corpus could
never have shown it.

Existing rows default to `invoice` / in force, which is what they were
implicitly assumed to be. Re-index a corpus to get real values.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policy_obligations",
        sa.Column("schema_name", sa.Text(), nullable=False, server_default="invoice"),
    )
    op.add_column(
        "policy_obligations",
        sa.Column("in_force", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # The coverage check reads by org, schema and force together.
    op.create_index(
        "ix_policy_obligations_scope",
        "policy_obligations",
        ["org_id", "schema_name", "in_force"],
    )


def downgrade() -> None:
    op.drop_index("ix_policy_obligations_scope", table_name="policy_obligations")
    op.drop_column("policy_obligations", "in_force")
    op.drop_column("policy_obligations", "schema_name")
