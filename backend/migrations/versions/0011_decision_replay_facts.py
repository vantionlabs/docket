"""record the facts a decision turned on, not prose about them

`ApplyRails` says "what the model proposed and what the system decided are
separate facts, both recorded". Only the second one was. The proposal, the
coverage verdict and the coverage recall were computed, written into the
workflow's node output, and left in an events JSON blob — one queryable row
out of five thousand.

That is enough to review a decision and not enough to ask anything of the
history. "If the auto-approve limit moved to EUR 2,500, which of the last
five thousand decisions would change?" is answerable from stored facts and
no model calls, because the rails are deterministic — but only if the input
to the rails was kept.

Backfill: where `rail_notes` is empty, no rail moved the outcome, so the
proposal is the outcome. Every branch of `apply_rails` that changes an
outcome also appends a note, so this is exact rather than a guess. Rows
where the rails did fire keep NULL, and replay reports them as unreplayable
instead of assuming.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("proposed_outcome", sa.Text(), nullable=True))
    op.add_column(
        "decisions",
        sa.Column("coverage_complete", sa.Boolean(), nullable=True),
    )
    op.add_column("decisions", sa.Column("coverage_recall", sa.Numeric(4, 3), nullable=True))

    op.execute(
        """
        UPDATE decisions
           SET proposed_outcome = outcome
         WHERE proposed_outcome IS NULL
           AND (rail_notes IS NULL OR cardinality(rail_notes) = 0)
        """
    )


def downgrade() -> None:
    op.drop_column("decisions", "coverage_recall")
    op.drop_column("decisions", "coverage_complete")
    op.drop_column("decisions", "proposed_outcome")
