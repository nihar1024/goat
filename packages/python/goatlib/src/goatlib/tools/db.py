"""Database operations for Windmill tool outputs.

This module handles all PostgreSQL operations for tool results:
- Creating layer metadata in customer.layer
- Linking layers to projects in customer.layer_project
- Updating project layer_order

These operations are shared across all tools (buffer, clip, join, etc.)
to avoid code duplication in Windmill scripts.
"""

import json
import logging
import uuid as uuid_module
from enum import Enum
from typing import Any, Literal, Self

import asyncpg
from pydantic import BaseModel, Field, model_validator

from goatlib.models.bundle import (
    BundleStatus,
)
from goatlib.tools.style import get_default_style

logger = logging.getLogger(__name__)


def normalize_geometry_type(geom_type: str | None) -> str | None:
    """Normalize DuckDB geometry type to GOAT schema enum value.

    DuckDB ST_GeometryType returns uppercase like 'POINT', 'LINESTRING', 'POLYGON'.
    GOAT schema expects lowercase: 'point', 'line', 'polygon'.

    Args:
        geom_type: Geometry type from DuckDB (e.g., 'POINT', 'MULTIPOLYGON')

    Returns:
        Normalized type ('point', 'line', 'polygon') or None
    """
    if not geom_type:
        return None

    geom_upper = geom_type.upper()

    if "POINT" in geom_upper:
        return "point"
    elif "LINE" in geom_upper or "STRING" in geom_upper:
        return "line"
    elif "POLYGON" in geom_upper:
        return "polygon"

    return None


class FeatureGeometryType(str, Enum):
    """Feature layer geometry types. Mirrors core.db.models.layer.FeatureGeometryType."""

    point = "point"
    line = "line"
    polygon = "polygon"


class LayerRecord(BaseModel):
    """Pydantic model mirroring customer.layer constraints.

    Validates data before INSERT to catch issues early instead of
    writing broken records to the database.
    """

    id: uuid_module.UUID
    user_id: uuid_module.UUID
    folder_id: uuid_module.UUID
    name: str = Field(min_length=1)
    type: Literal["feature", "raster", "table"]
    feature_layer_type: Literal["standard", "tool", "street_network"] | None = None
    feature_layer_geometry_type: FeatureGeometryType | None = None
    extent_wkt: str | None = None
    size: int = 0
    properties: dict[str, Any] | None = None
    other_properties: dict[str, Any] | None = None
    thumbnail_url: str | None = None
    tool_type: str | None = None
    job_id: uuid_module.UUID | None = None

    @model_validator(mode="after")
    def feature_layer_requires_geometry(self: Self) -> Self:
        """Feature layers must have a geometry type."""
        if self.type == "feature" and self.feature_layer_geometry_type is None:
            raise ValueError(
                "Feature layers require feature_layer_geometry_type "
                "(point, line, or polygon)"
            )
        return self


class LayerProjectRecord(BaseModel):
    """Pydantic model mirroring customer.layer_project constraints."""

    layer_id: uuid_module.UUID
    project_id: uuid_module.UUID
    name: str = Field(min_length=1, max_length=255)
    order: int = 0
    properties: dict[str, Any] | None = None
    other_properties: dict[str, Any] | None = None


class ToolDatabaseService:
    """Handles all database operations for tool outputs.

    Usage:
        pool = await asyncpg.create_pool(...)
        db = ToolDatabaseService(pool)

        await db.create_layer(layer_id=..., user_id=..., ...)
        await db.add_to_project(layer_id=..., project_id=..., ...)
    """

    def __init__(self: Self, pool: asyncpg.Pool, schema: str = "customer") -> None:
        """Initialize database service.

        Args:
            pool: asyncpg connection pool
            schema: Database schema name (default: customer)
        """
        self.pool = pool
        self.schema = schema

    async def get_project_folder_id(self: Self, project_id: str) -> str | None:
        """Get the folder_id for a project.

        Args:
            project_id: Project UUID

        Returns:
            folder_id or None if project not found
        """
        row = await self.pool.fetchrow(
            f"SELECT folder_id FROM {self.schema}.project WHERE id = $1",
            uuid_module.UUID(project_id),
        )
        if row:
            return str(row["folder_id"])
        return None

    async def create_layer(
        self: Self,
        layer_id: str,
        user_id: str,
        folder_id: str,
        name: str,
        layer_type: str = "feature",
        feature_layer_type: str | None = "tool",
        geometry_type: str | None = None,
        extent_wkt: str | None = None,
        feature_count: int = 0,
        size: int = 0,
        properties: dict[str, Any] | None = None,
        other_properties: dict[str, Any] | None = None,
        thumbnail_url: str
        | None = "https://assets.plan4better.de/img/goat_new_dataset_thumbnail.png",
        tool_type: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a layer record in customer.layer.

        Args:
            layer_id: UUID for the new layer
            user_id: Owner user UUID
            folder_id: Parent folder UUID
            name: Layer display name
            layer_type: "feature" or "table"
            feature_layer_type: "standard", "tool", "street_network", or None for tables
            geometry_type: "point", "line", "polygon", or None (will be normalized)
            extent_wkt: Spatial extent as WKT string
            feature_count: Number of features
            size: Size of the layer data in bytes
            properties: Layer properties (style, etc.)
            other_properties: Additional properties
            thumbnail_url: Layer thumbnail URL (defaults to standard thumbnail)
            tool_type: Tool type that created this layer (e.g., "catchment_area")
            job_id: Windmill job ID that created this layer

        Returns:
            The properties dict used (either provided or generated default)
        """
        # Normalize geometry type (POINT -> point, LINESTRING -> line, etc.)
        normalized_geom = normalize_geometry_type(geometry_type)

        # Validate all fields through the Pydantic model before touching the DB
        record = LayerRecord(
            id=uuid_module.UUID(layer_id),
            user_id=uuid_module.UUID(user_id),
            folder_id=uuid_module.UUID(folder_id),
            name=name,
            type=layer_type,
            feature_layer_type=feature_layer_type,
            feature_layer_geometry_type=normalized_geom,
            extent_wkt=extent_wkt,
            size=size,
            properties=properties,
            other_properties=other_properties,
            thumbnail_url=thumbnail_url,
            tool_type=tool_type,
            job_id=uuid_module.UUID(job_id) if job_id else None,
        )

        # Generate default style if no properties provided
        if properties is None and normalized_geom:
            properties = get_default_style(normalized_geom)

        # Convert dicts to JSON strings for JSONB columns
        properties_json = json.dumps(properties) if properties else None
        other_props_json = json.dumps(other_properties) if other_properties else None

        await self.pool.execute(
            f"""
            INSERT INTO {self.schema}.layer (
                id, user_id, folder_id, name, type, feature_layer_type,
                feature_layer_geometry_type, extent,
                size, properties, other_properties, thumbnail_url,
                tool_type, job_id, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7,
                CASE WHEN $8::text IS NOT NULL
                    THEN ST_Multi(ST_GeomFromText($8::text, 4326))
                    ELSE NULL
                END,
                $9, $10::jsonb, $11::jsonb, $12, $13, $14,
                NOW(), NOW()
            )
            """,
            record.id,
            record.user_id,
            record.folder_id,
            record.name,
            record.type,
            record.feature_layer_type,
            record.feature_layer_geometry_type.value
            if record.feature_layer_geometry_type
            else None,
            record.extent_wkt,
            record.size,
            properties_json,
            other_props_json,
            record.thumbnail_url,
            record.tool_type,
            record.job_id,
        )
        logger.info(
            f"Created layer: {layer_id} ({name}) in folder {folder_id} "
            f"with {feature_count} features, size={size} bytes"
        )
        return properties

    async def get_bundle_name(self: Self, bundle_id: str) -> str | None:
        """Return the bundle's display name (customer.bundle.name)."""
        row = await self.pool.fetchrow(
            f"SELECT name FROM {self.schema}.bundle WHERE id = $1",
            uuid_module.UUID(bundle_id),
        )
        return row["name"] if row else None

    async def delete_bundle(self: Self, bundle_id: str) -> None:
        """Remove a bundle row. Its artifact rows go with it (FK cascade).

        Used when an import fails: the layers it managed to write are removed
        first, so what is left is a bundle that holds nothing and can never be
        completed — there is no retry that could fill it in. The Windmill job
        carries the failure, so nothing is lost by removing the row.
        """
        await self.pool.execute(
            f"DELETE FROM {self.schema}.bundle WHERE id = $1",
            uuid_module.UUID(bundle_id),
        )
        logger.info(f"Deleted bundle {bundle_id}")

    async def update_package_status(
        self: Self,
        bundle_id: str,
        status: "BundleStatus | str",
    ) -> None:
        """Update a bundle's processing status."""
        status_value = getattr(status, "value", status)
        await self.pool.execute(
            f"""
            UPDATE {self.schema}.bundle
            SET status = $2, updated_at = NOW()
            WHERE id = $1
            """,
            uuid_module.UUID(bundle_id),
            status_value,
        )
        logger.info(f"Bundle {bundle_id} status -> {status_value}")

    async def update_package_metadata(
        self: Self,
        bundle_id: str,
        metadata: dict,
    ) -> None:
        """Write the provenance fields a source stated about itself.

        Merged into ``bundle.dataset_metadata``, so a field the source is
        silent about keeps whatever the owner authored — the same guarantee as
        before, now expressed by the JSONB concatenation rather than by
        assembling one assignment per column.
        """
        allowed = (
            "lineage",
            "geographical_code",
            "distributor_name",
            "distributor_email",
            "distribution_url",
            "license",
            "attribution",
            "data_reference_year",
        )
        unknown = set(metadata) - set(allowed)
        if unknown:
            raise ValueError(
                f"Not bundle metadata fields: {', '.join(sorted(unknown))}"
            )
        if not metadata:
            return

        await self.pool.execute(
            f"""
            UPDATE {self.schema}.bundle
            SET dataset_metadata =
                    COALESCE(dataset_metadata, '{{}}'::jsonb) || $2::jsonb,
                updated_at = NOW()
            WHERE id = $1
            """,
            uuid_module.UUID(bundle_id),
            json.dumps(metadata),
        )

    async def create_artifact(
        self: Self,
        bundle_id: str,
        kind: str,
        build_status: str = "building",
        job_id: str | None = None,
    ) -> str:
        """Create or reclaim the bundle_artifact row for (bundle_id, kind).

        Upserts against the (bundle_id, kind) unique constraint: a rebuild or a
        retried import takes over the existing row instead of dying on it.

        Only ``build_status`` is touched. ``revision`` and ``storage_path`` are
        left as they were, so a rebuild that fails or is superseded leaves the
        previous artifact still pointing at its own file and its own revision —
        which is what keeps a working graph usable for the whole build rather
        than taking it offline the moment a rebuild starts.
        Returns the row id."""
        kind_value = getattr(kind, "value", kind)
        status_value = getattr(build_status, "value", build_status)
        row = await self.pool.fetchrow(
            f"""
            INSERT INTO {self.schema}.bundle_artifact (
                bundle_id, kind, build_status, job_id, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (bundle_id, kind) DO UPDATE SET
                build_status = EXCLUDED.build_status,
                job_id = EXCLUDED.job_id,
                updated_at = NOW()
            RETURNING id
            """,
            uuid_module.UUID(bundle_id),
            kind_value,
            status_value,
            uuid_module.UUID(job_id) if job_id else None,
        )
        logger.info(
            f"Artifact {row['id']} ({kind_value}) for bundle {bundle_id}: "
            f"{status_value}"
        )
        return str(row["id"])

    async def set_artifact_build_status(
        self: Self, artifact_id: str, status: str
    ) -> None:
        """Record what an artifact's build attempt did.

        Only the outcome: where the file landed and which revision it came from
        are written by ``publish_artifact_if_current``, and only for the build
        that won. A failed or superseded attempt must not touch them, or it
        would take the previous good artifact with it.
        """
        status_value = getattr(status, "value", status)
        await self.pool.execute(
            f"""
            UPDATE {self.schema}.bundle_artifact
            SET build_status = $2, updated_at = NOW()
            WHERE id = $1
            """,
            uuid_module.UUID(artifact_id),
            status_value,
        )
        logger.info(f"Artifact {artifact_id} build -> {status_value}")

    async def mark_bundle_artifacts_failed(self: Self, bundle_id: str) -> None:
        """Mark every artifact row of a bundle failed.

        For a build that dies before reaching any specific artifact row (the
        export or the builder itself raised): without this the rows stay
        'building' and consumers keep promising an update that is not running,
        instead of saying the update failed."""
        await self.pool.execute(
            f"""
            UPDATE {self.schema}.bundle_artifact
            SET build_status = 'failed', updated_at = NOW()
            WHERE bundle_id = $1
            """,
            uuid_module.UUID(bundle_id),
        )

    async def set_layer_field_config(
        self: Self, layer_id: str, field_config: "dict[str, Any]"
    ) -> None:
        """Replace a layer's field_config JSONB.

        The same blob geoapi's column endpoints maintain — written here so an
        importer can declare a computed column at creation time, which those
        endpoints cannot do (they only ever edit a layer that already exists).
        """
        await self.pool.execute(
            f"UPDATE {self.schema}.layer SET field_config = $2::jsonb WHERE id = $1",
            uuid_module.UUID(layer_id),
            json.dumps(field_config),
        )

    async def get_bundle_artifact(
        self: Self, bundle_id: str, kind: str
    ) -> "dict | None":
        """Stored path, status and provenance of a bundle's artifact of a kind.

        ``layers_revision`` comes back alongside the artifact's own ``revision``
        so a caller can tell whether the file still matches the layers. That
        comparison is the real answer; the stored status only records what the
        last build attempt did. Reading both means a layer write whose
        stale-marking never landed cannot leave a tool routing on a graph that
        no longer matches the data.
        """
        kind_value = getattr(kind, "value", kind)
        row = await self.pool.fetchrow(
            f"""
            SELECT a.storage_path, a.build_status, a.revision, b.layers_revision
            FROM {self.schema}.bundle_artifact a
            JOIN {self.schema}.bundle b ON b.id = a.bundle_id
            WHERE a.bundle_id = $1 AND a.kind = $2
            LIMIT 1
            """,
            uuid_module.UUID(bundle_id),
            kind_value,
        )
        return dict(row) if row else None

    async def get_bundle(self: Self, bundle_id: str) -> "dict":
        """Type and owner of a bundle, for a build that was handed only an id."""
        row = await self.pool.fetchrow(
            f"""
            SELECT bundle_type, user_id, layers_revision
            FROM {self.schema}.bundle WHERE id = $1
            """,
            uuid_module.UUID(bundle_id),
        )
        if row is None:
            raise ValueError(f"Bundle {bundle_id} not found")
        return dict(row)

    async def get_bundle_revision(self: Self, bundle_id: str) -> int:
        """Current layers_revision of a bundle."""
        row = await self.pool.fetchrow(
            f"SELECT layers_revision FROM {self.schema}.bundle WHERE id = $1",
            uuid_module.UUID(bundle_id),
        )
        if row is None:
            raise ValueError(f"Bundle {bundle_id} not found")
        return int(row["layers_revision"])

    async def bump_bundle_revision(self: Self, bundle_id: str) -> int:
        """Advance a bundle's layers_revision, returning the new value."""
        row = await self.pool.fetchrow(
            f"""
            UPDATE {self.schema}.bundle
            SET layers_revision = layers_revision + 1, updated_at = NOW()
            WHERE id = $1
            RETURNING layers_revision
            """,
            uuid_module.UUID(bundle_id),
        )
        if row is None:
            raise ValueError(f"Bundle {bundle_id} not found")
        return int(row["layers_revision"])

    async def publish_artifact_if_current(
        self: Self,
        artifact_id: str,
        bundle_id: str,
        built_revision: int,
        storage_path: str,
        size: int,
    ) -> "tuple[bool, str | None]":
        """Mark an artifact ready, unless the layers have moved on since.

        The revision comparison sits in the WHERE clause, so there is no window
        between checking and writing for a concurrent save to slip through.

        Returns (published, displaced_path): the path this build replaced, so
        the caller can remove a file nothing points at any more. Only the build
        that wins the comparison gets one, so two concurrent rebuilds cannot
        both decide to delete the same file.
        """
        row = await self.pool.fetchrow(
            f"""
            WITH displaced AS (
                -- No FOR UPDATE: every CTE and the update share one snapshot,
                -- so this reads the path being replaced. A locking clause here
                -- would find the row already updated by this same command and
                -- return nothing, so the displaced file would never be removed.
                SELECT storage_path FROM {self.schema}.bundle_artifact
                WHERE id = $1
            ), current AS (
                UPDATE {self.schema}.bundle_artifact a
                SET build_status = 'complete',
                    storage_path = $3,
                    size = $4,
                    revision = $5,
                    updated_at = NOW()
                FROM {self.schema}.bundle b
                WHERE a.id = $1 AND b.id = $2 AND a.bundle_id = b.id
                  AND b.layers_revision = $5
                RETURNING a.id
            )
            SELECT
                EXISTS (SELECT 1 FROM current) AS published,
                (SELECT storage_path FROM displaced) AS displaced_path
            """,
            uuid_module.UUID(artifact_id),
            uuid_module.UUID(bundle_id),
            storage_path,
            size,
            built_revision,
        )
        if row is None or not row["published"]:
            return False, None
        displaced = row["displaced_path"]
        return True, (displaced if displaced != storage_path else None)

    async def list_bundle_layers(self: Self, bundle_id: str) -> "list[dict]":
        """Role and layer id of each member layer of a bundle."""
        rows = await self.pool.fetch(
            f"""
            SELECT role, layer_id FROM {self.schema}.bundle_layer
            WHERE bundle_id = $1 ORDER BY id
            """,
            uuid_module.UUID(bundle_id),
        )
        return [dict(r) for r in rows]

    async def add_layer_to_package(
        self: Self,
        bundle_id: str,
        layer_id: str,
        role: str | None = None,
    ) -> None:
        """Link a layer to a bundle with its role
        (customer.bundle_layer)."""
        await self.pool.execute(
            f"""
            INSERT INTO {self.schema}.bundle_layer (
                bundle_id, layer_id, role
            ) VALUES ($1, $2, $3)
            """,
            uuid_module.UUID(bundle_id),
            uuid_module.UUID(layer_id),
            role,
        )
        logger.info(f"Linked layer {layer_id} to bundle {bundle_id} as role={role}")

    async def add_to_project(
        self: Self,
        layer_id: str,
        project_id: str,
        name: str,
        properties: dict[str, Any] | None = None,
        other_properties: dict[str, Any] | None = None,
        group_id: int | None = None,
        order: int | None = None,
    ) -> int:
        """Link a layer to a project.

        Creates a record in customer.layer_project and updates the
        project's layer_order to include the new layer at the top.

        Args:
            layer_id: Layer UUID to link
            project_id: Project UUID to link to
            name: Display name for the layer in this project
            properties: Layer properties for this project context
            other_properties: Additional properties
            group_id: Layer group to place the link in (e.g. a bundle-backed
                group); None leaves the layer at the project root
            order: Position in the project's single tree-wide order sequence.
                None keeps the default of 0 and puts the layer at the top of
                layer_order, which is what a tool's output layer wants; giving one
                places the layer at that position and at the bottom instead.

        Returns:
            layer_project_id: The ID of the created link record
        """
        # Validate through Pydantic model before touching the DB
        record = LayerProjectRecord(
            layer_id=uuid_module.UUID(layer_id),
            project_id=uuid_module.UUID(project_id),
            name=name,
            properties=properties,
            other_properties=other_properties,
        )

        properties_json = json.dumps(properties) if properties else None
        other_props_json = json.dumps(other_properties) if other_properties else None

        # Create the layer_project link ("order" is non-nullable)
        row = await self.pool.fetchrow(
            f"""
            INSERT INTO {self.schema}.layer_project (
                layer_id, project_id, name, "order", properties, other_properties,
                layer_project_group_id, created_at, updated_at
            )
            VALUES ($1, $2, $3, $7, $4::jsonb, $5::jsonb, $6, NOW(), NOW())
            RETURNING id
            """,
            record.layer_id,
            record.project_id,
            record.name,
            properties_json,
            other_props_json,
            group_id,
            order if order is not None else 0,
        )
        layer_project_id = row["id"]

        # An explicitly ordered layer belongs at the bottom (it is placing itself
        # below what is already there); otherwise the newest layer goes on top.
        placement = (
            "array_append(COALESCE(layer_order, ARRAY[]::int[]), $1)"
            if order is not None
            else "array_prepend($1, COALESCE(layer_order, ARRAY[]::int[]))"
        )
        await self.pool.execute(
            f"""
            UPDATE {self.schema}.project
            SET layer_order = {placement},
                updated_at = NOW()
            WHERE id = $2
            """,
            layer_project_id,
            uuid_module.UUID(project_id),
        )

        logger.info(
            f"Added layer {layer_id} to project {project_id} "
            f"(layer_project_id={layer_project_id})"
        )
        return layer_project_id

    async def create_bundle_project_group(
        self: Self, project_id: str, bundle_id: str, name: str
    ) -> tuple[int, int]:
        """Create a bundle-backed layer group in a project (locked membership),
        placed below everything already there. Returns ``(id, order)`` — the
        caller needs the order to place the members directly beneath it.

        Groups and layers share one tree-wide "order" sequence — the layer panel
        writes it by flattening the whole tree — so the maximum is taken over both.
        Reading only the groups drops the bundle in among the existing layers."""
        row = await self.pool.fetchrow(
            f"""
            INSERT INTO {self.schema}.layer_project_group (
                project_id, bundle_id, name, "order", created_at, updated_at
            )
            VALUES (
                $1, $2, $3,
                GREATEST(
                    COALESCE((SELECT MAX("order") FROM {self.schema}.layer_project_group
                              WHERE project_id = $1), -1),
                    COALESCE((SELECT MAX("order") FROM {self.schema}.layer_project
                              WHERE project_id = $1), -1)
                ) + 1,
                NOW(), NOW()
            )
            RETURNING id, "order"
            """,
            uuid_module.UUID(project_id),
            uuid_module.UUID(bundle_id),
            name,
        )
        logger.info(
            f"Created bundle group {row['id']} for bundle {bundle_id} "
            f"in project {project_id} at order {row['order']}"
        )
        return row["id"], row["order"]

    async def delete_layer_project_group(self: Self, group_id: int) -> None:
        """Delete a project layer group (cascades its layer_project links). Used
        to roll back a partially-created bundle group on failure."""
        await self.pool.execute(
            f"DELETE FROM {self.schema}.layer_project_group WHERE id = $1",
            int(group_id),
        )

    async def delete_layer(self: Self, layer_id: str) -> None:
        """Delete a layer record from customer.layer.

        Note: This only deletes the metadata. DuckLake data should be
        deleted separately via DuckLakeManager.

        Args:
            layer_id: UUID of the layer to delete
        """
        await self.pool.execute(
            f"DELETE FROM {self.schema}.layer WHERE id = $1",
            uuid_module.UUID(layer_id),
        )
        logger.info(f"Deleted layer: {layer_id}")

    async def get_layer_info(self: Self, layer_id: str) -> dict[str, Any] | None:
        """Get layer information from the database.

        Args:
            layer_id: Layer UUID

        Returns:
            Dict with layer info (id, name, user_id, etc.) or None if not found
        """
        row = await self.pool.fetchrow(
            f"""
            SELECT id, name, user_id, folder_id, type, feature_layer_type,
                   feature_layer_geometry_type
            FROM {self.schema}.layer
            WHERE id = $1
            """,
            uuid_module.UUID(layer_id),
        )
        if row:
            return {
                "id": str(row["id"]),
                "name": row["name"],
                # NULL for a catalog layer, which belongs to nobody here.
                "user_id": str(row["user_id"]) if row["user_id"] else None,
                "folder_id": str(row["folder_id"]) if row["folder_id"] else None,
                "type": row["type"],
                "feature_layer_type": row["feature_layer_type"],
                "geometry_type": row["feature_layer_geometry_type"],
            }
        return None

    async def get_project_layer_name_by_id(
        self: Self, layer_project_id: int
    ) -> str | None:
        """Layer name (customer.layer_project.name) by the project-layer PK."""
        row = await self.pool.fetchrow(
            f"SELECT name FROM {self.schema}.layer_project WHERE id = $1",
            int(layer_project_id),
        )
        return row["name"] if row and row["name"] else None
