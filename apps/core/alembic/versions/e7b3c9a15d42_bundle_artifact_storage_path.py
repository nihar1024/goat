"""bundle_artifact: s3_key -> storage_path

Artifacts moved from object storage to the data volume (next to DuckLake and
tiles), so the column holds a path relative to the bundles data dir rather than
an S3 key. Existing keys cannot be reinterpreted as paths, so they are cleared
and the artifacts rebuilt.

Revision ID: e7b3c9a15d42
Revises: c4a1f2d90b17
Create Date: 2026-08-24 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e7b3c9a15d42'
down_revision = 'c4a1f2d90b17'
branch_labels = None
depends_on = None

SCHEMA = "customer"
TABLE = "bundle_artifact"


def _columns(bind: sa.engine.Connection) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(TABLE, schema=SCHEMA)}


def upgrade():
    cols = _columns(op.get_bind())
    if "storage_path" not in cols:
        if "s3_key" in cols:
            op.alter_column(
                TABLE, "s3_key", new_column_name="storage_path", schema=SCHEMA
            )
        else:
            op.add_column(
                TABLE,
                sa.Column("storage_path", sa.Text(), nullable=True),
                schema=SCHEMA,
            )
    # An S3 key is not a data-volume path. Blanking it marks the artifact
    # unbuilt so the next build writes to the volume, rather than leaving a
    # path that resolves nowhere.
    op.execute(
        sa.text(
            f'UPDATE {SCHEMA}.{TABLE} SET storage_path = NULL, status = \'pending\' '
            f"WHERE storage_path IS NOT NULL AND storage_path LIKE 'users/%'"
        )
    )


def downgrade():
    cols = _columns(op.get_bind())
    if "storage_path" in cols and "s3_key" not in cols:
        op.alter_column(
            TABLE, "storage_path", new_column_name="s3_key", schema=SCHEMA
        )
