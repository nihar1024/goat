"""add provenance metadata to bundle

Revision ID: c4a1f2d90b17
Revises: b3e1f7c94a20
Create Date: 2026-08-21 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4a1f2d90b17'
down_revision = 'b3e1f7c94a20'
branch_labels = None
depends_on = None

SCHEMA = "customer"
TABLE = "bundle"

COLUMNS = (
    ("lineage", sa.Text()),
    ("geographical_code", sa.Text()),
    ("distributor_name", sa.Text()),
    ("distributor_email", sa.Text()),
    ("distribution_url", sa.Text()),
    ("license", sa.Text()),
    ("attribution", sa.Text()),
    ("data_reference_year", sa.Integer()),
)


def _columns(bind: sa.engine.Connection) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(TABLE, schema=SCHEMA)}


def upgrade():
    # Fresh databases get these columns from the `init` create_all baseline; add
    # them only on existing (pre-feature) databases.
    cols = _columns(op.get_bind())
    for name, type_ in COLUMNS:
        if name not in cols:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True), schema=SCHEMA)


def downgrade():
    cols = _columns(op.get_bind())
    for name, _ in reversed(COLUMNS):
        if name in cols:
            op.drop_column(TABLE, name, schema=SCHEMA)
