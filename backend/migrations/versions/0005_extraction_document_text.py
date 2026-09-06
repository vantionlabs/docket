"""store the parsed text an extraction was made from

The decision detail screen (spec section 15) highlights each field's source
span inside the document, so it needs the text. Re-parsing a PDF per page
view would be slow and is not guaranteed to produce the same text twice.

The stronger reason is provenance: storing the exact text the verbatim
check ran against means an auditor can re-run that check a year later and
get the same answer. A span that verified against text nobody kept is a
claim, not a record.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "extractions",
        sa.Column("document_text", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("extractions", "document_text")
