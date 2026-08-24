"""Catalog back-references on customer.layer.

Adds the identity of a promoted catalog layer: which catalog item it came
from and at which version. The partial unique index is the promote-on-use
idempotency mechanism — a concurrent promote of the same (item, version)
conflicts here, and the loser reuses the winner's row.

IF NOT EXISTS throughout: the squashed `init` baseline creates the schema from
live model metadata, so a fresh install already has these columns when this
revision runs.

Revision ID: a1c4b2d9e001
Revises: init
"""

from alembic import op

from core.core.config import settings

revision = "a1c4b2d9e001"
down_revision = "init"
branch_labels = None
depends_on = None

SCHEMA = settings.SCHEMA


def upgrade() -> None:
    op.execute(
        f'ALTER TABLE "{SCHEMA}".layer '
        f"ADD COLUMN IF NOT EXISTS catalog_external_uid TEXT NULL"
    )
    op.execute(
        f'ALTER TABLE "{SCHEMA}".layer '
        f"ADD COLUMN IF NOT EXISTS catalog_version TEXT NULL"
    )
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS uq_layer_catalog_identity "
        f'ON "{SCHEMA}".layer (catalog_external_uid, catalog_version) '
        f"WHERE catalog_external_uid IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(f'DROP INDEX IF EXISTS "{SCHEMA}".uq_layer_catalog_identity')
    op.execute(f'ALTER TABLE "{SCHEMA}".layer DROP COLUMN IF EXISTS catalog_version')
    op.execute(
        f'ALTER TABLE "{SCHEMA}".layer DROP COLUMN IF EXISTS catalog_external_uid'
    )
