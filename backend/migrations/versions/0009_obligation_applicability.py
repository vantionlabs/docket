"""obligations carry the subject they bear on

`Dimension` says what kind of rule an obligation is; it cannot say what the
rule is ABOUT. "Catering and hospitality commitments up to EUR 50,000 may be
approved by a department head" is an `amount` rule, it governs invoices, and
it is in force — and it has nothing to say about a cleaning invoice.

Every invoice triggers `amount`, so all fifteen of the delegation matrix's
category ladders were required for every decision and the repair step pulled
eight of them into the evidence each time. Irrelevant clauses in the evidence
are how a grounding judge gets talked into rejecting a citation.

Empty means unconditional, which is what every existing row was implicitly
assumed to be. Re-index a corpus to get real values.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policy_obligations",
        sa.Column("applies_when", sa.ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("policy_obligations", "applies_when")
