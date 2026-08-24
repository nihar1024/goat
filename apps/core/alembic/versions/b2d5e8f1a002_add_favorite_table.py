"""Generic per-user favourites.

One row per (user, kind, id). The favourited item may live outside this
database entirely — catalog items live in the STAC mirror — so item_id is an
opaque text key with no foreign key.

Guarded by an existence check: the squashed `init` baseline creates the
schema from live model metadata, so a fresh install already has the table
when this revision runs.

Revision ID: b2d5e8f1a002
Revises: 7732fb7ef953
"""

import sqlalchemy as sa
from alembic import op

from core.core.config import settings

revision = "b2d5e8f1a002"
down_revision = "7732fb7ef953"
branch_labels = None
depends_on = None

SCHEMA = settings.SCHEMA


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("favorite", schema=SCHEMA):
        return
    op.execute(
        f"""
        CREATE TABLE "{SCHEMA}".favorite (
            user_id    uuid        NOT NULL
                REFERENCES "{SCHEMA}"."user"(id) ON DELETE CASCADE,
            item_type  text        NOT NULL,
            item_id    text        NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, item_type, item_id)
        )
        """
    )
    op.execute(
        f'CREATE INDEX ix_favorite_user_type ON "{SCHEMA}".favorite (user_id, item_type)'
    )


def downgrade() -> None:
    op.execute(f'DROP TABLE IF EXISTS "{SCHEMA}".favorite')
