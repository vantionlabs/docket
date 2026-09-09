"""extractions record deterministic checks, not only arithmetic

`arithmetic_ok` and `arithmetic_failures` were named for the only check that
existed when they were added. The concept has since become "what can be
decided without a model", and `evals/check_rule.py` made the gap matter: a
duplicate invoice is answerable by a query and was being left to the model's
judgement, and there was nowhere truthful to record the answer.

A tender's version of arithmetic is chronology; an invoice's is VAT and a
repeated invoice number. All of them are the same argument — a model asked
to do it will sometimes do it wrong, and there is no reason to ask — and all
of them feed the same rail. So the columns take the name of the concept.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-09
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("extractions", "arithmetic_ok", new_column_name="checks_ok")
    op.alter_column("extractions", "arithmetic_failures", new_column_name="check_failures")


def downgrade() -> None:
    op.alter_column("extractions", "checks_ok", new_column_name="arithmetic_ok")
    op.alter_column("extractions", "check_failures", new_column_name="arithmetic_failures")
