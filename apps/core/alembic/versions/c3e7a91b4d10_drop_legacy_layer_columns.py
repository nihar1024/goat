"""drop the legacy columns and tables, and unown the catalog layers

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

**Scenarios go entirely**, tables included: ``customer.scenario``,
``scenario_feature``, ``scenario_scenario_feature`` and
``project.active_scenario_id``. All scenario code is gone as of this revision,
and the product no longer needs the data (owner's call, made knowing there are
rows in production).

Measured on the same 12,281-layer copy: 214 scenarios across 118 owners, 246
features, 245 links, 160 projects still pointing at one; newest scenario
2026-06-16, newest feature 2026-03-24.

``scenario_feature`` is the last table using the generic-column scheme — 109
``text_attr1``/``jsonb_attr1``-style columns, 34 of them holding data — and the
only thing that ever said what those columns *meant* was ``layer.attribute_mapping``,
which this same revision drops. So the payload stops being interpretable here
whether or not the table survives; keeping it would preserve bytes, not
information. Take a ``pg_dump`` of the three tables before running this if that
turns out to matter.

``customer.bundle`` keeps its provenance, but as one ``dataset_metadata``
document rather than eight flat columns — there an importer really does fill it,
reading ``feed_publisher_name`` out of a GTFS feed. The bundle revision
(``12d658d174ae``) was changed to create the table in that shape, which is right
for a fresh database but reaches no environment that already ran it, so the
transition happens here: add the column, fold the eight columns into it, drop
them and the never-used ``properties``.

**A catalog layer now has no owner.** ``layer.user_id`` and ``layer.folder_id``
become nullable and are set to NULL for every promoted catalog layer, and the
synthetic identity that used to hold them — the ``catalog@goat.local`` user, its
``GOAT Catalog`` organization (invented phone number, industry and 2^31 quotas)
and its ``catalog`` folder — is deleted.

NULL is the truth: a catalog dataset belongs to the provider that published it,
not to anyone here. Every consumer already behaves correctly for it — the
storage trigger looks up the owner's organization and finds none, so catalog
bytes are billed to nobody; "My Content" filters on ``user_id = you`` and so
never lists them; and ``check_layer`` already grants read through
``catalog_external_uid IS NOT NULL``, never through the user.

Order matters here: ``layer.folder_id`` is ``ON DELETE CASCADE``, so the rows
are detached **before** the folder and user are removed. Dropping the folder
first would take the layers with it, and they are live in users' projects.

The legacy ``catalog@plan4better.de`` account is untouched: it is a real login
with 85 working layers and 13 projects of its own, and it still owns the 66
``in_catalog`` layers.

Revision ID: c3e7a91b4d10
Revises: b2d5e8f1a002
Create Date: 2026-08-27 11:05:00.000000

"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
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

# The eight columns `customer.bundle` used to carry, folded into one document.
_BUNDLE_PROVENANCE: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("lineage", sa.Text()),
    ("geographical_code", sa.Text()),
    ("distributor_name", sa.Text()),
    ("distributor_email", sa.Text()),
    ("distribution_url", sa.Text()),
    ("license", sa.Text()),
    ("attribution", sa.Text()),
    ("data_reference_year", sa.Integer()),
)

# Children first: `scenario_scenario_feature` references both of the others.
_SCENARIO_TABLES = ("scenario_scenario_feature", "scenario_feature", "scenario")

# `scenario_feature` stored a feature's attributes in fixed generic slots, one
# family per type. Regenerated rather than spelled out — 109 columns is not worth
# a literal.
_SCENARIO_FEATURE_ATTRS: tuple[tuple[str, int, sa.types.TypeEngine], ...] = (
    ("integer_attr", 25, sa.Integer()),
    ("float_attr", 25, sa.Float()),
    ("text_attr", 25, sa.Text()),
    ("bigint_attr", 5, sa.BigInteger()),
    ("jsonb_attr", 10, postgresql.JSONB(astext_type=sa.Text())),
    ("boolean_attr", 10, sa.Boolean()),
    ("arrint_attr", 3, postgresql.ARRAY(sa.Integer())),
    ("arrfloat_attr", 3, postgresql.ARRAY(sa.Float())),
    ("arrtext_attr", 3, postgresql.ARRAY(sa.Text())),
    ("timestamp_attr", 3, sa.DateTime(timezone=False)),
)


def _timestamps() -> tuple[sa.Column, ...]:
    """The `DateTimeBase` pair every table in this schema carries."""
    return (
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
    )


def upgrade() -> None:
    # A fresh database is built from the live models by `init`, so none of this
    # exists there — hence the guards rather than bare drops.
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Every drop below takes ACCESS EXCLUSIVE on customer.layer for the whole
    # alembic transaction. The drops are metadata-only and fast, but *acquiring*
    # the lock is not: one long-lived reader (a pinned geoapi connection, a
    # running tool) blocks it, and then every query on the table queues behind
    # the waiting migration. Fail fast instead and let the operator retry.
    op.execute("SET lock_timeout = '5s'")

    columns = {c["name"] for c in inspector.get_columns("layer", schema=SCHEMA)}
    for name, _type in _COLUMNS:
        if name in columns:
            op.drop_column("layer", name, schema=SCHEMA)

    # After the FK column, so the drop cannot fail on a dependency.
    if "data_store" in inspector.get_table_names(schema=SCHEMA):
        op.drop_table("data_store", schema=SCHEMA)

    project_columns = {
        c["name"] for c in inspector.get_columns("project", schema=SCHEMA)
    }
    if "active_scenario_id" in project_columns:
        op.drop_column("project", "active_scenario_id", schema=SCHEMA)

    tables = set(inspector.get_table_names(schema=SCHEMA))
    for name in _SCENARIO_TABLES:
        if name in tables:
            op.drop_table(name, schema=SCHEMA)

    # `customer.bundle`'s own revision now creates `dataset_metadata` directly,
    # so a fresh database arrives with it and skips all of this. A database that
    # already ran that revision still has the eight flat columns and needs the
    # values moved before they are dropped.
    if "bundle" in tables:
        bundle_columns = {
            c["name"] for c in inspector.get_columns("bundle", schema=SCHEMA)
        }
        if "dataset_metadata" not in bundle_columns:
            op.add_column(
                "bundle",
                sa.Column("dataset_metadata", postgresql.JSONB(astext_type=sa.Text())),
                schema=SCHEMA,
            )
            # jsonb_strip_nulls so an untouched bundle gets `{}`, not eight nulls.
            present = [c for c, _ in _BUNDLE_PROVENANCE if c in bundle_columns]
            if present:
                pairs = ", ".join(f"'{c}', {c}" for c in present)
                op.execute(
                    f"""
                    UPDATE {SCHEMA}.bundle
                    SET dataset_metadata = jsonb_strip_nulls(jsonb_build_object({pairs}))
                    """
                )
        for name, _type in _BUNDLE_PROVENANCE:
            if name in bundle_columns:
                op.drop_column("bundle", name, schema=SCHEMA)
        # Never read or written anywhere.
        if "properties" in bundle_columns:
            op.drop_column("bundle", "properties", schema=SCHEMA)

    # A catalog layer belongs to the provider that published it, not to anyone
    # here, so it gets no owner.
    op.alter_column("layer", "user_id", nullable=True, schema=SCHEMA)
    op.alter_column("layer", "folder_id", nullable=True, schema=SCHEMA)
    op.execute(
        f"""
        UPDATE {SCHEMA}.layer
        SET user_id = NULL, folder_id = NULL
        WHERE catalog_external_uid IS NOT NULL
        """
    )

    # Detached first: layer.folder_id is ON DELETE CASCADE, so removing the
    # folder while rows still point at it would delete layers that are live in
    # users' projects.
    op.execute(
        f"""
        WITH identity AS (
            SELECT id, organization_id FROM {SCHEMA}."user"
            WHERE email = 'catalog@goat.local'
        ),
        dropped_folders AS (
            DELETE FROM {SCHEMA}.folder
            WHERE user_id IN (SELECT id FROM identity)
        ),
        dropped_roles AS (
            DELETE FROM {SCHEMA}.user_role
            WHERE user_id IN (SELECT id FROM identity)
        ),
        dropped_user AS (
            DELETE FROM {SCHEMA}."user" WHERE id IN (SELECT id FROM identity)
        )
        DELETE FROM {SCHEMA}.organization
        WHERE id IN (SELECT organization_id FROM identity WHERE organization_id IS NOT NULL)
        """
    )


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

    existing_fks = {
        fk["name"] for fk in inspector.get_foreign_keys("layer", schema=SCHEMA)
    }
    if "layer_data_store_id_fkey" not in existing_fks:
        op.create_foreign_key(
            "layer_data_store_id_fkey",
            "layer",
            "data_store",
            ["data_store_id"],
            ["id"],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
        )

    tables = set(inspector.get_table_names(schema=SCHEMA))
    if "scenario" not in tables:
        op.create_table(
            "scenario",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            *_timestamps(),
            schema=SCHEMA,
        )

    if "scenario_feature" not in tables:
        op.create_table(
            "scenario_feature",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("geom", Geometry(srid=4326), nullable=True),
            sa.Column("edit_type", sa.Text(), nullable=False),
            sa.Column(
                "layer_project_id",
                sa.Integer(),
                sa.ForeignKey(f"{SCHEMA}.layer_project.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("feature_id", sa.Text(), nullable=True),
            sa.Column("h3_3", sa.Integer(), nullable=True),
            sa.Column("h3_6", sa.Integer(), nullable=True),
            *(
                sa.Column(f"{prefix}{n}", type_, nullable=True)
                for prefix, count, type_ in _SCENARIO_FEATURE_ATTRS
                for n in range(1, count + 1)
            ),
            *_timestamps(),
            schema=SCHEMA,
        )
        op.create_index(
            "scenario_feature_geom_idx",
            "scenario_feature",
            ["geom"],
            unique=False,
            postgresql_using="gist",
            schema=SCHEMA,
        )

    if "scenario_scenario_feature" not in tables:
        op.create_table(
            "scenario_scenario_feature",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "scenario_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(f"{SCHEMA}.scenario.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "scenario_feature_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(f"{SCHEMA}.scenario_feature.id", ondelete="CASCADE"),
                nullable=False,
            ),
            *_timestamps(),
            schema=SCHEMA,
        )

    project_columns = {
        c["name"] for c in inspector.get_columns("project", schema=SCHEMA)
    }
    if "active_scenario_id" not in project_columns:
        op.add_column(
            "project",
            sa.Column("active_scenario_id", postgresql.UUID(as_uuid=True)),
            schema=SCHEMA,
        )

    # The owner columns go back to NOT NULL, which means the catalog layers
    # need an owner again — so the synthetic identity is recreated and they are
    # reattached to it. Not restored: the organization's invented profile.
    # User first with no organization, then the organization pointing back at
    # it, then the link — organization.contact_user_id is NOT NULL, so the two
    # cannot be inserted in one step.
    op.execute(
        f"""
        INSERT INTO {SCHEMA}."user" (id, email, firstname, lastname, avatar,
            created_at, updated_at)
        VALUES ('ca7a1000-0000-4000-8000-000000000001', 'catalog@goat.local',
            'GOAT', 'Catalog', '', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO {SCHEMA}.organization (id, name, avatar, on_trial, plan_name,
            total_credits, total_storage, total_projects, total_editors,
            total_viewers, type, size, industry, department, use_case,
            phone_number, location, region, stripe_id, suspended,
            contact_user_id, created_at, updated_at)
        VALUES ('ca7a1000-0000-4000-8000-000000000003', 'GOAT Catalog', '', FALSE,
            'goat_starter', 2147483647, 2147483647, 2147483647, 2147483647,
            2147483647, 'other', '1-10', 'other', 'general', 'other',
            '+0000000000', 'system', 'EU', '', FALSE,
            'ca7a1000-0000-4000-8000-000000000001', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}."user"
        SET organization_id = 'ca7a1000-0000-4000-8000-000000000003'
        WHERE id = 'ca7a1000-0000-4000-8000-000000000001'
        """
    )
    op.execute(
        f"""
        INSERT INTO {SCHEMA}.folder (id, user_id, name, created_at, updated_at)
        VALUES ('ca7a1000-0000-4000-8000-000000000002',
            'ca7a1000-0000-4000-8000-000000000001', 'catalog', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.layer
        SET user_id = 'ca7a1000-0000-4000-8000-000000000001',
            folder_id = 'ca7a1000-0000-4000-8000-000000000002'
        WHERE catalog_external_uid IS NOT NULL
        """
    )
    op.alter_column("layer", "folder_id", nullable=False, schema=SCHEMA)
    op.alter_column("layer", "user_id", nullable=False, schema=SCHEMA)

    bundle_columns = {c["name"] for c in inspector.get_columns("bundle", schema=SCHEMA)}
    for name, type_ in _BUNDLE_PROVENANCE:
        if name not in bundle_columns:
            op.add_column(
                "bundle", sa.Column(name, type_, nullable=True), schema=SCHEMA
            )
    if "properties" not in bundle_columns:
        op.add_column(
            "bundle",
            sa.Column("properties", postgresql.JSONB(astext_type=sa.Text())),
            schema=SCHEMA,
        )
    if "dataset_metadata" in bundle_columns:
        sets = ", ".join(
            f"{c} = (dataset_metadata ->> '{c}')::{'integer' if c == 'data_reference_year' else 'text'}"
            for c, _ in _BUNDLE_PROVENANCE
        )
        op.execute(
            f"UPDATE {SCHEMA}.bundle SET {sets} WHERE dataset_metadata IS NOT NULL"
        )
        op.drop_column("bundle", "dataset_metadata", schema=SCHEMA)
