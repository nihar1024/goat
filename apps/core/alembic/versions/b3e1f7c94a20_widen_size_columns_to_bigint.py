"""widen bundle_artifact.size to bigint

Revision ID: b3e1f7c94a20
Revises: 0975d67ad88f
Create Date: 2026-08-16 09:12:44.310277

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b3e1f7c94a20'
down_revision = '0975d67ad88f'
branch_labels = None
depends_on = None

SCHEMA = "customer"
TABLE = "bundle_artifact"
COLUMN = "size"


def _column_type(bind: sa.engine.Connection) -> str | None:
    for c in sa.inspect(bind).get_columns(TABLE, schema=SCHEMA):
        if c["name"] == COLUMN:
            return type(c["type"]).__name__.upper()
    return None


def upgrade():
    # A bundle's graph artifact is a whole network and can exceed INTEGER's
    # 2.1 GB ceiling. Fresh databases already have BIGINT from the `init`
    # create_all baseline, so alter only where the old type is still in place.
    if _column_type(op.get_bind()) == "INTEGER":
        op.alter_column(
            TABLE, COLUMN, type_=sa.BigInteger(), existing_nullable=True, schema=SCHEMA
        )


def downgrade():
    # Values above 2^31-1 cannot round-trip; the cast raises rather than
    # truncating silently.
    if _column_type(op.get_bind()) == "BIGINT":
        op.alter_column(
            TABLE, COLUMN, type_=sa.Integer(), existing_nullable=True, schema=SCHEMA
        )
