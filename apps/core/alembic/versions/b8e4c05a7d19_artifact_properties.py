"""bundle_artifact: what a build knows about its own output

Some facts about an artifact are known only to the build that produced it and
are wanted by whoever uses it. A PT timetable is built for a window of dates
taken from the feed's calendar — outside it the timetable answers every journey
with "no service" — and the feed itself is not kept, so once the build ends the
window is only knowable if the build wrote it down. A date picker offered
against that timetable needs exactly those bounds.

One JSONB column rather than a typed one per fact: these are per-kind and
per-builder, and a column each would mean a migration each. The trade is that
nothing checks the shape, so the read path treats it as free-form — a value it
does not recognise is reported as absent rather than failing the request.

`none_as_null` on the column: without it SQLAlchemy stores a Python None as the
JSON value `null`, which is not an object, and every consumer then has to guard
a shape that should simply have been absent.

Existing rows are left NULL: their builds predate this and there is nothing to
backfill from — the feed a timetable came from is gone. They read as "no
properties recorded", which is true.

Revision ID: b8e4c05a7d19
Revises: a7c31f9d6b52
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8e4c05a7d19"
down_revision = "a7c31f9d6b52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bundle_artifact",
        sa.Column("properties", postgresql.JSONB(), nullable=True),
        schema="customer",
    )


def downgrade() -> None:
    op.drop_column("bundle_artifact", "properties", schema="customer")
