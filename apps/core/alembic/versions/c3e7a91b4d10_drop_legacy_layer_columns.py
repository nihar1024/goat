"""drop the legacy columns from layer, and the data_store table

Seventeen nullable columns on ``customer.layer`` and one whole table, all left
over from things GOAT no longer has: the old catalog page, the shared-wide-table
storage layout, and an upload path that no longer records what it did.

**The old catalog's schema** — ``lineage``, ``positional_accuracy``,
``attribute_accuracy``, ``completeness``, ``geographical_code``,
``language_code``, ``distributor_name``, ``distributor_email``,
``distribution_url``, ``license``, ``attribution``, ``data_reference_year``,
``data_category``. These were its filter dropdowns and facet counts, hardcoded
onto every layer row. Measured on a 12,281-layer copy, 109 rows carry any of
them, 66 of those being the old ``in_catalog`` layers.

Nothing replaces them, because a layer has no metadata of its own to hold:

* a user's uploaded dataset is its name, description and tags — publishing one
  to the catalog will be its own job, not a set of columns;
* a promoted catalog layer already carries the catalog's own record verbatim in
  ``other_properties.catalog_item``, in the catalog's vocabulary
  (``license: "DL-DE-BY-2.0"``, ``publisher: "Landesamt für Umwelt (LfU)"``).

Translating one into the other was considered and rejected: ``DDN2`` is an enum
invented for that dropdown, so the mapping would swap a real versioned licence
identifier for an internal code, lose the ``2.0``, and need a lookup maintained
for as long as the catalog publishes anything new.

**``attribute_mapping``** mapped generic physical column names (``text_attr1``,
``integer_attr2``, …) back to the user's own, from when every layer's data lived
in shared wide tables. Since the DuckLake rework each layer is its own table
holding the real names, and the migration applied the mapping: a layer whose
mapping reads ``{"text_attr1": "category"}`` has a ``category`` column. What
survived was inconsistent (8,944 of 12,281 rows non-empty, mostly identity maps)
and unread — the last reader, ``get_scenario_features``, treated the JSON as
``{real: generic}`` while every stored row is ``{generic: real}``, so it emitted
``sf."category" AS "text_attr1"`` against a table with no such column. The field
list the frontend uses comes from the DuckLake table schema plus
``field_config``.

**``upload_reference_system``** and **``upload_file_type``** describe an upload
no current code path records: nothing writes either (0 and 30 rows), no read
schema exposes them, and the metadata form filtered them out.

**``data_store_id``** and ``customer.data_store`` — the table has no CRUD, no
endpoint and no router (5 rows, 2 referenced by a layer); the column is never
written and never read, and the relationship existed only to satisfy the
back-reference.

Deliberately kept:

* ``tool_type`` and ``job_id``, populated on 9,828 and 11,451 layers. Nothing
  reads them today, but they record which tool and which Windmill job produced a
  layer, across most of the table. That is provenance, not cruft.
* ``in_catalog``. Its 66 rows are the old catalog's layers and ``check_layer``
  still grants access through it, so retiring it means first deciding what
  identifies those layers instead.
* ``customer.scenario``, ``scenario_feature``, ``scenario_scenario_feature`` and
  ``project.active_scenario_id`` (214 / 246 / — / 160 rows). All scenario code is
  gone as of this revision, but dropping the data is a separate call.

``customer.bundle`` keeps its ``dataset_metadata`` document: there an importer
really does fill it, reading ``feed_publisher_name`` out of a GTFS feed.

Revision ID: c3e7a91b4d10
Revises: b2d5e8f1a002
Create Date: 2026-08-27 11:05:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from core.core.config import settings

# revision identifiers, used by Alembic.
revision = "c3e7a91b4d10"
down_revision = "b2d5e8f1a002"
branch_labels = None
depends_on = None

SCHEMA = settings.SCHEMA

_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    # the old catalog's metadata vocabulary
    ("lineage", sa.Text()),
    ("positional_accuracy", sa.Text()),
    ("attribute_accuracy", sa.Text()),
    ("completeness", sa.Text()),
    ("geographical_code", sa.Text()),
    ("language_code", sa.Text()),
    ("distributor_name", sa.Text()),
    ("distributor_email", sa.Text()),
    ("distribution_url", sa.Text()),
    ("license", sa.Text()),
    ("attribution", sa.Text()),
    ("data_reference_year", sa.Integer()),
    ("data_category", sa.Text()),
    # the generic-column scheme and the vestigial upload/data-store fields
    ("attribute_mapping", postgresql.JSONB(astext_type=sa.Text())),
    ("upload_reference_system", sa.Integer()),
    ("upload_file_type", sa.Text()),
    ("data_store_id", postgresql.UUID(as_uuid=True)),
)


def upgrade() -> None:
    # A fresh database is built from the live models by `init`, so none of this
    # exists there — hence the guards rather than bare drops.
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {c["name"] for c in inspector.get_columns("layer", schema=SCHEMA)}
    for name, _type in _COLUMNS:
        if name in columns:
            op.drop_column("layer", name, schema=SCHEMA)

    # After the FK column, so the drop cannot fail on a dependency.
    if "data_store" in inspector.get_table_names(schema=SCHEMA):
        op.drop_table("data_store", schema=SCHEMA)


def downgrade() -> None:
    """Restore the columns and the table, empty.

    The values are not recoverable — `upgrade` drops them — and would not be
    worth recovering: the mappings were identity maps or pointed at columns that
    no longer exist, and the catalog record some of the metadata was copied from
    lives in `other_properties.catalog_item` in a different vocabulary. This
    exists so the revision is reversible in shape, not in content.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "data_store" not in inspector.get_table_names(schema=SCHEMA):
        op.create_table(
            "data_store",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("type", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            schema=SCHEMA,
        )

    columns = {c["name"] for c in inspector.get_columns("layer", schema=SCHEMA)}
    for name, type_ in _COLUMNS:
        if name not in columns:
            op.add_column("layer", sa.Column(name, type_, nullable=True), schema=SCHEMA)

    op.create_foreign_key(
        "layer_data_store_id_fkey",
        "layer",
        "data_store",
        ["data_store_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
