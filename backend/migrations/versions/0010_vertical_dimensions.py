"""dimensions belong to a vertical, not to a hard-coded list

0007 closed `policy_obligations.dimension` with a CHECK naming the nine
invoice dimensions. That was right — a dimension nothing evaluates must not
sit in the index looking like a checked rule — and wrong about where the
list lives. A tender has `deadline`, `security` and `certification`; an
invoice has `vat` and `duplicate`; they share `scope` and `escalation`. With
the list in a CHECK, adding a document type means a migration, which is the
fork spec section 3 says this pipeline should not need.

So the set stays closed, and moves into a table the registry keeps current.
`vertical_dimensions` holds one row per (schema_name, dimension); obligations
reference it by composite foreign key. Registering a vertical and calling
`sync_vertical_dimensions` is now the whole of adding one — no DDL.

This also adds `source_documents.vertical`, so the decide workflow can ask
the document what it is instead of importing a constant.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# Seeded literally rather than imported from app.verticals: a migration has
# to replay identically in a year, and the registry will have moved on.
SEED = {
    "invoice": (
        "amount",
        "purchase_order",
        "supplier",
        "currency",
        "vat",
        "payment_terms",
        "duplicate",
        "scope",
        "escalation",
    ),
    "tender": (
        "value",
        "deadline",
        "penalty",
        "security",
        "certification",
        "insurance",
        "materials",
        "exclusion",
        "scope",
        "escalation",
    ),
}


def upgrade() -> None:
    table = op.create_table(
        "vertical_dimensions",
        sa.Column("schema_name", sa.Text(), primary_key=True),
        sa.Column("dimension", sa.Text(), primary_key=True),
    )
    op.bulk_insert(
        table,
        [
            {"schema_name": schema, "dimension": dimension}
            for schema, dimensions in SEED.items()
            for dimension in dimensions
        ],
    )

    # `governs="other"` is the extractor saying a clause belongs to a
    # different policy than the one being indexed for. Those rows are never
    # loaded — `load_obligations` filters on schema_name — so they have only
    # ever been dead weight, and no vertical will ever claim their
    # dimensions. Deleting them is what makes the foreign key possible.
    op.execute("DELETE FROM policy_obligations WHERE schema_name NOT IN ('invoice', 'tender')")

    # An obligation whose dimension is not one this vertical evaluates is a
    # rule that will never be checked. The FK is what stops it being stored.
    op.drop_constraint("ck_policy_obligations_dimension", "policy_obligations")
    op.create_foreign_key(
        "fk_policy_obligations_dimension",
        "policy_obligations",
        "vertical_dimensions",
        ["schema_name", "dimension"],
        ["schema_name", "dimension"],
    )

    op.add_column(
        "source_documents",
        sa.Column("vertical", sa.Text(), nullable=False, server_default="invoice"),
    )


def downgrade() -> None:
    op.drop_column("source_documents", "vertical")
    op.drop_constraint("fk_policy_obligations_dimension", "policy_obligations")
    op.execute("DELETE FROM policy_obligations WHERE schema_name <> 'invoice'")
    op.create_check_constraint(
        "ck_policy_obligations_dimension",
        "policy_obligations",
        "dimension IN ('amount','purchase_order','supplier','currency','vat',"
        "'payment_terms','duplicate','scope','escalation')",
    )
    op.drop_table("vertical_dimensions")
