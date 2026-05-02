"""add resource_grant table and folder sharing roles

Revision ID: f1a2b3c4d5e6
Revises: e8bd0e42b8eb
Create Date: 2026-05-01 00:00:00.000000

"""

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e8bd0e42b8eb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add organization_id to accounts.user stub (missing from core stub)
    op.execute("""
        ALTER TABLE accounts."user"
            ADD COLUMN IF NOT EXISTS organization_id UUID
                REFERENCES accounts.organization(id) ON DELETE SET NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_organization_id
            ON accounts."user" (organization_id)
    """)

    # Add role_id to accounts.user_team
    op.execute("""
        ALTER TABLE accounts.user_team
            ADD COLUMN IF NOT EXISTS role_id UUID
                REFERENCES accounts.role(id) ON DELETE SET NULL
    """)

    # Create resource_grant table in accounts schema
    op.execute("""
        CREATE TABLE IF NOT EXISTS accounts.resource_grant (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            resource_type   VARCHAR(50)  NOT NULL,
            resource_id     UUID         NOT NULL,
            grantee_type    VARCHAR(50)  NOT NULL,
            grantee_id      UUID         NOT NULL,
            role_id         UUID         NOT NULL REFERENCES accounts.role(id) ON DELETE CASCADE,
            granted_by      UUID         NOT NULL REFERENCES accounts."user"(id) ON DELETE CASCADE,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
            UNIQUE (resource_type, resource_id, grantee_type, grantee_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_resource_grant_resource
            ON accounts.resource_grant (resource_type, resource_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_resource_grant_grantee
            ON accounts.resource_grant (grantee_type, grantee_id)
    """)

    # Insert folder roles (idempotent — role table has no UNIQUE on name)
    # op.execute("""
    #     INSERT INTO accounts.role (name, created_at, updated_at)
    #     SELECT v.name, now(), now()
    #     FROM (VALUES ('folder-viewer'), ('folder-editor')) AS v(name)
    #     WHERE NOT EXISTS (
    #         SELECT 1 FROM accounts.role r WHERE r.name = v.name
    #     )
    # """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accounts.resource_grant")
    op.execute(
        "DELETE FROM accounts.role WHERE name IN ('folder-viewer', 'folder-editor')"
    )
    op.execute("ALTER TABLE accounts.user_team DROP COLUMN IF EXISTS role_id")
    op.execute('ALTER TABLE accounts."user" DROP COLUMN IF EXISTS organization_id')
