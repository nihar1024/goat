"""bundle layers revision and artifact revision

Revision ID: f1a7c30d5e94
Revises: e7b3c9a15d42
Create Date: 2026-08-25

``bundle.layers_revision`` is bumped on every member-layer edit. An artifact
build records the revision it read, and publishes only if that is still the
current one — so a build overtaken by a later save discards its output instead
of publishing a graph that no longer matches the layers.
"""

import sqlalchemy as sa
from alembic import op

from core.core.config import settings

revision = "f1a7c30d5e94"
down_revision = "e7b3c9a15d42"
branch_labels = None
depends_on = None

SCHEMA = settings.SCHEMA


def upgrade() -> None:
    op.add_column(
        "bundle",
        sa.Column(
            "layers_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "bundle_artifact",
        sa.Column("revision", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("bundle_artifact", "revision", schema=SCHEMA)
    op.drop_column("bundle", "layers_revision", schema=SCHEMA)
