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
    # One statement, so the pairing is materialised once. The earlier
    # version inserted orgs and memberships separately and joined them by
    # row_number() over each table: with every row created in the same
    # transaction, `created_at` ties and the two orderings fall back to
    # random uuids, so users got each other's org names. Every user still
    # ended up owning exactly one org, which is why it survived a structural
    # check and only showed up against realistic emails.
    op.execute(
        """
        WITH pairs AS (
            SELECT u.id AS user_id,
                   gen_random_uuid() AS org_id,
                   -- Mirrors _default_org_name in app/auth/orgs.py: a
                   -- company domain names the org, a consumer one names the
                   -- person. The two must agree, or a backfilled org is
                   -- named differently from one created at registration.
                   initcap(replace(replace(
                       CASE
                           WHEN lower(split_part(u.email, '@', 2)) IN (
                               'gmail.com', 'outlook.com', 'hotmail.com',
                               'icloud.com', 'proton.me'
                           )
                           THEN split_part(u.email, '@', 1)
                           ELSE split_part(split_part(u.email, '@', 2), '.', 1)
                       END, '-', ' '), '.', ' ')) AS org_name
            FROM users u
            WHERE NOT EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = u.id)
        ),
        created AS (
            INSERT INTO organizations (id, name, created_at)
            SELECT org_id, org_name, now() FROM pairs
            RETURNING id
        )
        INSERT INTO memberships (id, org_id, user_id, role, approval_limit, created_at)
        SELECT gen_random_uuid(), org_id, user_id, 'owner', NULL, now() FROM pairs
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
