"""Drop the bundle_type table and bundle.records

Two leftovers, both of which claimed to hold something and did not.

`bundle_type` was a reference table of one useful column — `type`, the target of
a foreign key from `bundle.bundle_type` — and one that was written by a seeder
and read by nothing. That second column, `structure`, was a projection of the
type specs in code, so it drifted the moment a spec changed; every consumer
resolves the live spec through `goatlib.models.bundle.get_spec` instead, which
is why nothing noticed. Its `type_definition`/`bundles` relationships were
declared on both models and used by neither.

Code is already the source of truth for the set of bundle types (see that
module's own docstring). Keeping the table meant a migration and a seed run to
add a type, and left a stale copy of the type's structure behind for the
trouble. The column stays `text`, validated on the way in by the
`BundleTypeName` enum on `BundleCreate`; the read models report it as stored, so
a value a release does not know reads back rather than failing the request.

`bundle.records` survived the rename from `dataset_package` — it is absent from
the model, written and read by nothing, and holds values on rows imported before
the rename.

Revision ID: a7c31f9d6b52
Revises: f6b2d84e1c47
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7c31f9d6b52"
down_revision = "f6b2d84e1c47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "bundle_bundle_type_fkey", "bundle", schema="customer", type_="foreignkey"
    )
    op.drop_table("bundle_type", schema="customer")
    op.drop_column("bundle", "records", schema="customer")


def downgrade() -> None:
    op.add_column(
        "bundle",
        sa.Column("records", postgresql.JSONB(), nullable=True),
        schema="customer",
    )
    op.create_table(
        "bundle_type",
        sa.Column("type", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("structure", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        schema="customer",
    )
    # Enough rows for the foreign key to be satisfiable, from the types the
    # bundles actually use. The content is a projection of the specs in code:
    # the release that owned this table refills it on boot from its own
    # `seed_bundle_types`, and inventing a `structure` here would recreate
    # exactly the drift the upgrade removed.
    op.execute(
        "INSERT INTO customer.bundle_type (type, name, structure) "
        "SELECT DISTINCT bundle_type, bundle_type, '{}'::jsonb "
        "FROM customer.bundle"
    )
    op.create_foreign_key(
        "bundle_bundle_type_fkey",
        "bundle",
        "bundle_type",
        ["bundle_type"],
        ["type"],
        source_schema="customer",
        referent_schema="customer",
        ondelete="RESTRICT",
    )
