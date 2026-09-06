"""orgs become required on the domain tables

M2 created `org_id` nullable, because nothing set it yet. M3 wires orgs
into the auth seam, so now everything does, and the column stops being
optional.

Backfill first: every existing user gets an org they own, and every row
they own inherits it. Then the constraints go on. Doing it in this order
means an existing database migrates rather than breaks, which is the whole
reason the columns were created early.

`document_chunks` and `source_documents` keep `org_id` NULLABLE on
purpose: they are the template's tables, not Docket's, and the template
has no orgs. The backport (spec section 14) is what makes them required
there, if it does at all.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Docket's own tables. These cannot exist without a tenant.
REQUIRED = ("intakes", "extractions", "decisions", "rules", "executions")


def upgrade() -> None:
    # 1. An org per existing user, named from the email like the app does.
    op.execute(
        """
        INSERT INTO organizations (id, name, created_at)
        SELECT gen_random_uuid(),
               initcap(replace(split_part(split_part(u.email, '@', 2), '.', 1), '-', ' ')),
               now()
        FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = u.id)
        """
    )

    # 2. Own it. The org just created for a user is the newest one with no
    #    members, matched back by row order.
    op.execute(
        """
        INSERT INTO memberships (id, org_id, user_id, role, approval_limit, created_at)
        SELECT gen_random_uuid(), o.id, u.id, 'owner', NULL, now()
        FROM (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn
            FROM organizations
            WHERE NOT EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = organizations.id)
        ) o
        JOIN (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn
            FROM users
            WHERE NOT EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = users.id)
        ) u ON u.rn = o.rn
        """
    )

    # 3. Inherit the tenant on every row that has an owner to inherit from.
    op.execute(
        """
        UPDATE source_documents d
        SET org_id = m.org_id
        FROM memberships m
        WHERE m.user_id = d.user_id AND d.org_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE document_chunks c
        SET org_id = m.org_id
        FROM memberships m
        WHERE m.user_id = c.user_id AND c.org_id IS NULL
        """
    )
    for table in ("intakes", "extractions", "decisions"):
        op.execute(
            f"""
            UPDATE {table} t
            SET org_id = d.org_id
            FROM source_documents d
            WHERE d.id = t.document_id AND t.org_id IS NULL
            """
        )
    op.execute(
        """
        UPDATE executions e
        SET org_id = d.org_id
        FROM decisions d
        WHERE d.id = e.decision_id AND e.org_id IS NULL
        """
    )

    # 4. A row with no tenant left cannot be attributed to one, and guessing
    #    would be worse than refusing. Nothing in a fresh database matches.
    for table in REQUIRED:
        op.execute(f"DELETE FROM {table} WHERE org_id IS NULL")
        op.alter_column(table, "org_id", nullable=False)


def downgrade() -> None:
    for table in REQUIRED:
        op.alter_column(table, "org_id", nullable=True)
