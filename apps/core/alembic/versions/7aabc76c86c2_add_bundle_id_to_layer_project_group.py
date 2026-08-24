"""add bundle_id to layer_project_group

Revision ID: 7aabc76c86c2
Revises: 12d658d174ae
Create Date: 2026-07-23 08:04:43.263478

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7aabc76c86c2'
down_revision = '12d658d174ae'
branch_labels = None
depends_on = None

SCHEMA = "customer"
TABLE = "layer_project_group"
COLUMN = "bundle_id"
INDEX = "ix_customer_layer_project_group_bundle_id"
FK = "layer_project_group_bundle_id_fkey"


def _has_column(bind: sa.engine.Connection) -> bool:
    return any(
        c["name"] == COLUMN
        for c in sa.inspect(bind).get_columns(TABLE, schema=SCHEMA)
    )


def upgrade():
    # Fresh databases get the column from the `init` create_all baseline; only
    # add it on existing (pre-feature) databases.
    bind = op.get_bind()
    if _has_column(bind):
        return
    op.add_column(TABLE, sa.Column(COLUMN, sa.UUID(), nullable=True), schema=SCHEMA)
    op.create_index(
        op.f(INDEX), TABLE, [COLUMN], unique=False, schema=SCHEMA
    )
    op.create_foreign_key(
        FK,
        TABLE,
        "bundle",
        [COLUMN],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )


def downgrade():
    bind = op.get_bind()
    if not _has_column(bind):
        return
    op.drop_constraint(FK, TABLE, schema=SCHEMA, type_="foreignkey")
    op.drop_index(op.f(INDEX), table_name=TABLE, schema=SCHEMA)
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
