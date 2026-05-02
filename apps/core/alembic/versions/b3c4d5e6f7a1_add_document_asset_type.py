"""add document asset type and folder_id to uploaded_asset

Revision ID: b3c4d5e6f7a1
Revises: f1a2b3c4d5e6
Create Date: 2026-05-02 00:00:00.000000

"""

from alembic import op

revision = "b3c4d5e6f7a1"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extend the asset_type enum with 'document'
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'document'")

    # 2. Add folder_id FK to uploaded_asset
    op.execute("""
        ALTER TABLE customer.uploaded_asset
            ADD COLUMN IF NOT EXISTS folder_id UUID
                REFERENCES customer.folder(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_uploaded_asset_folder_id
            ON customer.uploaded_asset (folder_id)
    """)


def downgrade() -> None:
    # Removing an enum value in PostgreSQL requires recreating the type —
    # intentionally left as no-op for safety.
    op.execute("DROP INDEX IF EXISTS customer.idx_uploaded_asset_folder_id")
    op.execute("ALTER TABLE customer.uploaded_asset DROP COLUMN IF EXISTS folder_id")
