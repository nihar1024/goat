"""bundle: a fresh row is 'processing', not 'ready'

The row is committed before its import job runs — it is the foreign key its
member layers and dependencies point at — so it exists holding nothing until the
job finishes. Defaulting to 'ready' claimed the opposite.

`status` also loses its 'failed' value in this release: an import that fails
deletes its own bundle, because nothing can complete a half-ingested one and the
job carries the failure. Rows written by earlier releases are left alone. They
still read back (the column is text and nothing coerces it into the enum), and
removing them is an operator's decision, not a migration's:

    DELETE FROM customer.bundle WHERE status = 'failed';

Revision ID: e5a1c73f9b28
Revises: d4f8b21c6a30
"""

from alembic import op

revision = "e5a1c73f9b28"
down_revision = "d4f8b21c6a30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE customer.bundle ALTER COLUMN status SET DEFAULT 'processing'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE customer.bundle ALTER COLUMN status SET DEFAULT 'ready'")
