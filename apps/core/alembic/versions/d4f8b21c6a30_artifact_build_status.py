"""bundle_artifact: status -> build_status

Currency stops being stored and becomes derived. `status` conflated two
questions — what the last build did, and whether the artifact still matches the
layers — and only the first is a fact the row can hold. The second is
`revision` vs the bundle's `layers_revision`, which is already recorded, so
storing it as well meant a second write on every layer change and one missed
write meant routing on a graph that no longer matched the data.

`ready` and `stale` both mean a build completed, and which of the two it is now
follows from the revisions. `pending` meant a row existed before anything was
built; nothing creates that state any more (the row is written when a build
starts), so the rows are mapped to `failed`, which is how the UI already offers
the way back.

Revision ID: d4f8b21c6a30
Revises: c3e7a91b4d10
"""

import sqlalchemy as sa
from alembic import op

revision = "d4f8b21c6a30"
down_revision = "c3e7a91b4d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "bundle_artifact",
        "status",
        new_column_name="build_status",
        server_default=None,
        schema="customer",
    )
    op.execute(
        """
        UPDATE customer.bundle_artifact
        SET build_status = CASE build_status
            WHEN 'ready' THEN 'complete'
            WHEN 'stale' THEN 'complete'
            WHEN 'pending' THEN 'failed'
            ELSE build_status
        END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE customer.bundle_artifact a
        SET build_status = CASE
            WHEN a.build_status <> 'complete' THEN a.build_status
            WHEN a.revision IS NOT NULL AND a.revision = b.layers_revision
                THEN 'ready'
            ELSE 'stale'
        END
        FROM customer.bundle b
        WHERE b.id = a.bundle_id
        """
    )
    op.alter_column(
        "bundle_artifact",
        "build_status",
        new_column_name="status",
        server_default=sa.text("'pending'"),
        schema="customer",
    )
