"""convert assettype enum column to varchar

Revision ID: c4d5e6f7a8b2
Revises: b3c4d5e6f7a1
Create Date: 2026-05-02 01:00:00.000000

"""

from alembic import op

revision = "c4d5e6f7a8b2"
down_revision = "b3c4d5e6f7a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert every schema's uploaded_asset.asset_type from native PostgreSQL
    # enum to VARCHAR(50) so asyncpg's string codec is used for both encode
    # and decode — the native enum codec caches valid values per connection and
    # rejects new values (like 'document') added after connect.
    #
    # The DO block handles test schemas (test_customer1, etc.) that also have
    # the column typed as assettype.  The customer schema may not have the
    # column at all (it was never added via migration), so we add it separately.
    op.execute("""
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT n.nspname AS schema_name,
                       c.relname AS table_name,
                       a.attname AS col_name
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                JOIN pg_type t ON a.atttypid = t.oid
                WHERE t.typname = 'assettype'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I.%I ALTER COLUMN %I TYPE VARCHAR(50) USING %I::VARCHAR',
                    r.schema_name, r.table_name, r.col_name, r.col_name
                );
            END LOOP;
        END $$
    """)

    # Add the column to the production customer schema if it's missing
    # (the table was created from an older model version that had no column).
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'customer'
                  AND table_name   = 'uploaded_asset'
                  AND column_name  = 'asset_type'
            ) THEN
                ALTER TABLE customer.uploaded_asset
                    ADD COLUMN asset_type VARCHAR(50) NOT NULL DEFAULT 'image';
                ALTER TABLE customer.uploaded_asset
                    ALTER COLUMN asset_type DROP DEFAULT;
            END IF;
        END $$
    """)

    op.execute("DROP TYPE IF EXISTS assettype")


def downgrade() -> None:
    op.execute("CREATE TYPE assettype AS ENUM ('image', 'icon', 'document')")
    op.execute("""
        ALTER TABLE customer.uploaded_asset
            ALTER COLUMN asset_type TYPE assettype
            USING asset_type::assettype
    """)
