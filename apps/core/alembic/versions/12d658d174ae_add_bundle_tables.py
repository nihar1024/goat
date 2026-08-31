"""add bundle tables

Bundles: a bundle is several member layers acquired and managed as one unit
(a GTFS feed, an Overture street-network extract). This creates the whole
bundle schema in its final shape — bundle_type, bundle, bundle_artifact,
bundle_dependency, bundle_layer, and the bundle_id back-reference on
layer_project_group.

The squashed `init` baseline builds the entire schema from the live SQLModel
metadata via create_all, so on a FRESH database these objects already exist by
the time this migration runs. init creates all model tables atomically, so the
presence of bundle_type is an all-or-nothing proxy for the rest: skip on fresh
DBs, create on existing (pre-bundle) DBs.

Revision ID: 12d658d174ae
Revises: init
Create Date: 2026-07-15 11:23:17.460624

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "12d658d174ae"
down_revision = "init"
branch_labels = None
depends_on = None

SCHEMA = "customer"
_PROBE_TABLE = "bundle_type"
_CREATED_AT_DEFAULT = sa.text(
    "to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', "
    "'YYYY-MM-DD\"T\"HH24:MI:SSOF')::timestamptz"
)


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(_PROBE_TABLE, schema=SCHEMA):
        return

    op.create_table(
        "bundle_type",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_CREATED_AT_DEFAULT,
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("structure", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("type"),
        schema=SCHEMA,
    )

    op.create_table(
        "bundle",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_CREATED_AT_DEFAULT,
            nullable=False,
        ),
        sa.Column("folder_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("bundle_type", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        # Dataset-level provenance, as one document rather than a column each.
        # The layer vocabulary it draws on is itself queued to collapse into
        # JSONB (docs/flat-layer-storage-todo.md), so a new table has no reason
        # to arrive in the shape being retired: nothing filters or joins on
        # these, importers already produce a sparse dict, and a source that
        # starts stating a new field costs no migration.
        sa.Column(
            "dataset_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("status", sa.Text(), server_default="ready", nullable=False),
        # Bumped on every member-layer edit; artifact builds record the
        # revision they read and publish only if it is still current.
        sa.Column(
            "layers_revision",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bundle_type"], ["customer.bundle_type.type"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["folder_id"], ["customer.folder.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["customer.user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_customer_bundle_bundle_type"),
        "bundle",
        ["bundle_type"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "bundle_artifact",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_CREATED_AT_DEFAULT,
            nullable=False,
        ),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("bundle_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        # Path on the bundles data volume, relative to the data dir.
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        # bundle.layers_revision the build read its member layers at.
        sa.Column("revision", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["bundle_id"], ["customer.bundle.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # (bundle_id, kind) is unique and indexes bundle_id as its leading
        # column, so bundle_id needs no separate index.
        sa.UniqueConstraint("bundle_id", "kind", name="uq_bundle_artifact_kind"),
        schema=SCHEMA,
    )

    op.create_table(
        "bundle_dependency",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bundle_id", sa.UUID(), nullable=False),
        sa.Column("depends_on_bundle_id", sa.UUID(), nullable=False),
        sa.Column("dependency_kind", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bundle_id"], ["customer.bundle.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_bundle_id"], ["customer.bundle.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bundle_id", "dependency_kind", name="uq_bundle_dependency_kind"
        ),
        schema=SCHEMA,
    )
    # Reverse lookup (dependents of a bundle) is not covered by the unique
    # constraint's leading column, so it keeps its own index.
    op.create_index(
        "idx_bundle_dependency_depends_on",
        "bundle_dependency",
        ["depends_on_bundle_id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "bundle_layer",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bundle_id", sa.UUID(), nullable=False),
        sa.Column("layer_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["bundle_id"], ["customer.bundle.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["layer_id"], ["customer.layer.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # (bundle_id, role) unique indexes bundle_id as its leading column.
        sa.UniqueConstraint("bundle_id", "role", name="uq_bundle_layer_role"),
        sa.UniqueConstraint("layer_id", name="uq_bundle_layer_layer"),
        schema=SCHEMA,
    )

    # Back-reference on the project layer group: a group that holds a bundle's
    # layers (locked membership).
    op.add_column(
        "layer_project_group",
        sa.Column("bundle_id", sa.UUID(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_customer_layer_project_group_bundle_id"),
        "layer_project_group",
        ["bundle_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "layer_project_group_bundle_id_fkey",
        "layer_project_group",
        "bundle",
        ["bundle_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_PROBE_TABLE, schema=SCHEMA):
        return
    op.drop_constraint(
        "layer_project_group_bundle_id_fkey",
        "layer_project_group",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_customer_layer_project_group_bundle_id"),
        table_name="layer_project_group",
        schema=SCHEMA,
    )
    op.drop_column("layer_project_group", "bundle_id", schema=SCHEMA)
    op.drop_table("bundle_layer", schema=SCHEMA)
    op.drop_index(
        "idx_bundle_dependency_depends_on",
        table_name="bundle_dependency",
        schema=SCHEMA,
    )
    op.drop_table("bundle_dependency", schema=SCHEMA)
    op.drop_table("bundle_artifact", schema=SCHEMA)
    op.drop_index(
        op.f("ix_customer_bundle_bundle_type"), table_name="bundle", schema=SCHEMA
    )
    op.drop_table("bundle", schema=SCHEMA)
    op.drop_table("bundle_type", schema=SCHEMA)
