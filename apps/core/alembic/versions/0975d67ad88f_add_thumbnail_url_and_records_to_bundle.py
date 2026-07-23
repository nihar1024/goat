"""add thumbnail_url and records to bundle

Revision ID: 0975d67ad88f
Revises: 7aabc76c86c2
Create Date: 2026-07-23 08:21:11.848444

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0975d67ad88f'
down_revision = '7aabc76c86c2'
branch_labels = None
depends_on = None

SCHEMA = "customer"
TABLE = "bundle"


def _columns(bind: sa.engine.Connection) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(TABLE, schema=SCHEMA)}


def upgrade():
    # Fresh databases get these columns from the `init` create_all baseline; add
    # them only on existing (pre-feature) databases.
    cols = _columns(op.get_bind())
    if "thumbnail_url" not in cols:
        op.add_column(
            TABLE, sa.Column("thumbnail_url", sa.Text(), nullable=True), schema=SCHEMA
        )
    if "records" not in cols:
        op.add_column(
            TABLE,
            sa.Column("records", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            schema=SCHEMA,
        )


def downgrade():
    cols = _columns(op.get_bind())
    if "records" in cols:
        op.drop_column(TABLE, "records", schema=SCHEMA)
    if "thumbnail_url" in cols:
        op.drop_column(TABLE, "thumbnail_url", schema=SCHEMA)
