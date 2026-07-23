"""Dataset-bundle import runner.

Ingests a validated source into DuckLake as member layers and creates the
bundle + membership rows. Reuses ``SimpleToolRunner``'s ingest
primitives (DuckLake connection, ``_ingest_to_ducklake``, postgres pool) and the
per-type importer plugin — so it stays type-agnostic and runs wherever the tools
run (Windmill, or any env with DuckLake + Postgres configured).

Boundary: this is the *mechanical* side (produce layers, write rows). Policy —
who may import, quota, the HTTP surface — stays in core, which triggers this.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel

from goatlib.bundles.artifacts import (
    ArtifactBuilderUnavailableError,
    get_artifact_builder,
)
from goatlib.bundles.importers import get_importer
from goatlib.bundles.importers.base import ValidationResult
from goatlib.io.converter import IOConverter
from goatlib.models.bundle import (
    BundleStatus,
    BundleTypeName,
    get_spec,
)
from goatlib.models.io import DatasetMetadata
from goatlib.tools.base import BaseToolRunner
from goatlib.tools.db import ToolDatabaseService, normalize_geometry_type
from goatlib.tools.style import get_default_style

logger = logging.getLogger(__name__)


class BundleValidationError(Exception):
    """Raised when the uploaded source fails validation against the type spec."""

    def __init__(self, validation: ValidationResult) -> None:
        self.validation = validation
        detail = "; ".join(validation.errors) or "Source failed validation"
        super().__init__(detail)


class ImportedLayer(BaseModel):
    role: str
    layer_id: str
    name: str
    layer_type: str
    geometry_type: Optional[str] = None
    feature_count: int = 0


class BundleImportResult(BaseModel):
    bundle_id: str
    bundle_type: str
    layers: List[ImportedLayer]


class BundleImportRunner(BaseToolRunner):
    """Multi-output ingest: source → member layers in DuckLake + bundle rows.

    Subclasses ``BaseToolRunner`` to reuse its ingest primitives
    (``_ingest_to_ducklake`` etc.), but drives them directly from
    ``run_import`` — the single-output ``run()``/``process()`` lifecycle is not
    used.
    """

    def process(self, params: Any, temp_dir: Path) -> "tuple[Path, DatasetMetadata]":
        raise NotImplementedError(
            "BundleImportRunner uses run_import(), not the single-output "
            "run()/process() lifecycle."
        )

    async def _cleanup_layers(
        self, db: ToolDatabaseService, user_id: str, layer_ids: List[str]
    ) -> None:
        """Best-effort removal of member layers created before a failure — their
        DuckLake tables and Postgres rows (which cascade the membership links) —
        so a partial import never leaves orphaned data behind."""
        if not layer_ids:
            return
        self.recycle_duckdb_connection()  # start from a clean connection for drops
        for layer_id in layer_ids:
            try:
                self.duckdb_con.execute(
                    f"DROP TABLE IF EXISTS {self.get_layer_table_path(user_id, layer_id)}"
                )
            except Exception as e:  # pragma: no cover - best-effort cleanup
                logger.warning("Cleanup: could not drop DuckLake table %s: %s", layer_id, e)
            try:
                await db.delete_layer(layer_id)
            except Exception as e:  # pragma: no cover - best-effort cleanup
                logger.warning("Cleanup: could not delete layer row %s: %s", layer_id, e)
        logger.info("Rolled back %d partially-imported layer(s)", len(layer_ids))

    async def _ingest_layers(
        self,
        db: ToolDatabaseService,
        *,
        source_path: str,
        bundle_type: "BundleTypeName | str",
        user_id: str,
        folder_id: str,
        bundle_id: str,
    ) -> List[ImportedLayer]:
        """Extract, ingest to DuckLake, and link each member layer. Assumes the
        bundle row already exists (FK target for the membership links).

        Member creation isn't a single transaction (DuckLake tables + separate
        Postgres rows), so on any failure we roll back the layers created so far
        to avoid orphaned tables/rows, then re-raise."""
        importer = get_importer(bundle_type)
        converter = IOConverter()
        imported: List[ImportedLayer] = []
        created_layer_ids: List[str] = []
        # Prefix member-layer names with the bundle name (e.g. "gtfs_fr Stops") so
        # they read cleanly and stay unique across bundles whose members share
        # standard names (stops, calendar, …).
        bundle_name = await db.get_bundle_name(bundle_id)
        with tempfile.TemporaryDirectory() as workdir:
            layers = importer.extract_layers(source_path, workdir)
            try:
                for i, extracted in enumerate(layers):
                    layer_id = str(uuid4())
                    # Tracked before ingest so a table created by a failing step
                    # is still dropped during cleanup.
                    created_layer_ids.append(layer_id)

                    # Importers may emit ready-to-ingest parquet (e.g. GTFS
                    # attribute tables) or a source file (GeoJSON/CSV) that needs
                    # conversion.
                    if extracted.file_path.endswith(".parquet"):
                        parquet_path = Path(extracted.file_path)
                    else:
                        parquet_path = Path(workdir) / f"out_{i}.parquet"
                        converter.to_parquet(
                            src_path=extracted.file_path,
                            out_path=str(parquet_path),
                            target_crs="EPSG:4326",
                        )
                    info = self._ingest_to_ducklake(
                        user_id=user_id, layer_id=layer_id, parquet_path=parquet_path
                    )

                    layer_name = (
                        f"{bundle_name} {extracted.name}"
                        if bundle_name
                        else extracted.name
                    )
                    await db.create_layer(
                        layer_id=layer_id,
                        user_id=user_id,
                        folder_id=folder_id,
                        name=layer_name,
                        layer_type=extracted.layer_type,
                        feature_layer_type=(
                            "standard" if extracted.layer_type == "feature" else None
                        ),
                        geometry_type=info.get("geometry_type"),
                        extent_wkt=info.get("extent_wkt"),
                        feature_count=info.get("feature_count", 0),
                        size=info.get("size", 0),
                    )
                    await db.add_layer_to_package(
                        bundle_id=bundle_id, layer_id=layer_id, role=extracted.role
                    )

                    imported.append(
                        ImportedLayer(
                            role=extracted.role,
                            layer_id=layer_id,
                            name=layer_name,
                            layer_type=extracted.layer_type,
                            geometry_type=info.get("geometry_type"),
                            feature_count=info.get("feature_count", 0),
                        )
                    )
                    # Each CREATE TABLE is its own DuckLake commit; recycling the
                    # connection between layers keeps the catalog cache bounded.
                    self.recycle_duckdb_connection()
            except Exception:
                await self._cleanup_layers(db, user_id, created_layer_ids)
                raise
        return imported

    async def _add_bundle_to_project(
        self,
        db: ToolDatabaseService,
        *,
        project_id: str,
        bundle_id: str,
        imported: List[ImportedLayer],
    ) -> None:
        """Place the freshly-imported member layers into a locked bundle-backed
        group in the given project (the upload-from-within-a-project flow).

        Each project layer gets the same default style the member layer was
        created with, so it matches adding the bundle to a project manually."""
        bundle_name = await db.get_bundle_name(bundle_id) or "Bundle"
        group_id = await db.create_bundle_project_group(
            project_id=project_id, bundle_id=bundle_id, name=bundle_name
        )
        try:
            for layer in imported:
                geom = normalize_geometry_type(layer.geometry_type)
                properties = get_default_style(geom) if geom else None
                await db.add_to_project(
                    layer_id=layer.layer_id,
                    project_id=project_id,
                    name=layer.name,
                    properties=properties,
                    group_id=group_id,
                )
        except Exception:
            # Roll back the partially-populated group (cascades its links) so a
            # failure never leaves a half-filled locked bundle group behind.
            await db.delete_layer_project_group(group_id)
            raise
        logger.info(
            "Added bundle %s to project %s (%d member layers)",
            bundle_id,
            project_id,
            len(imported),
        )

    async def _build_artifacts(
        self,
        db: ToolDatabaseService,
        *,
        bundle_id: str,
        bundle_type: "BundleTypeName | str",
        source_path: str,
        user_id: str,
    ) -> None:
        """Build and store the bundle type's derived artifacts (per spec).

        Each artifact is written to a temp file, uploaded to S3, and recorded as
        a ``bundle_artifact`` row (building → ready). A build failure propagates
        so the caller marks the bundle failed; a missing toolchain is skipped
        with a warning (the import still completes)."""
        assert self.settings is not None
        spec = get_spec(bundle_type)
        builder = get_artifact_builder(bundle_type)
        if not spec.artifacts or builder is None:
            return

        with tempfile.TemporaryDirectory() as workdir:
            try:
                built = builder.build(source_path=source_path, workdir=workdir)
            except ArtifactBuilderUnavailableError as e:
                logger.warning(
                    "Skipping artifact build for bundle %s: %s", bundle_id, e
                )
                return

            for art in built:
                kind_value = getattr(art.kind, "value", art.kind)
                artifact_id = await db.create_artifact(
                    bundle_id=bundle_id, kind=kind_value, status="building"
                )
                try:
                    s3_key = (
                        f"users/{user_id}/bundles/{bundle_id}"
                        f"/artifacts/{kind_value}.bin"
                    )
                    self.settings.get_s3_client().upload_file(
                        art.local_path, self.settings.s3_bucket_name, s3_key
                    )
                    await db.update_artifact_status(
                        artifact_id=artifact_id,
                        status="ready",
                        s3_key=s3_key,
                        size=art.size,
                    )
                    logger.info(
                        "Artifact %s for bundle %s stored at %s (%d bytes)",
                        kind_value,
                        bundle_id,
                        s3_key,
                        art.size,
                    )
                except Exception:
                    await db.update_artifact_status(
                        artifact_id=artifact_id, status="failed"
                    )
                    raise

    async def run_import(
        self,
        *,
        source_path: str,
        bundle_type: "BundleTypeName | str",
        user_id: str,
        folder_id: str,
        name: str,
        description: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        bundle_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> BundleImportResult:
        """Full import: validate, create the bundle, and ingest its layers.
        Used for direct/CLI runs where the bundle doesn't yet exist.

        When ``project_id`` is given, the imported bundle is also added to that
        project as a locked bundle-backed group."""
        assert self.settings is not None, "init_from_env()/init() must run first"

        type_value = BundleTypeName(bundle_type).value
        importer = get_importer(bundle_type)

        validation = importer.validate(source_path)
        if not validation.valid:
            raise BundleValidationError(validation)

        bundle_id = bundle_id or str(uuid4())
        pool = await self.get_postgres_pool()
        db = ToolDatabaseService(pool, schema=self.settings.customer_schema)
        try:
            await db.create_bundle(
                bundle_id=bundle_id,
                user_id=user_id,
                folder_id=folder_id,
                name=name,
                bundle_type=type_value,
                description=description,
                properties=properties,
            )
            imported = await self._ingest_layers(
                db,
                source_path=source_path,
                bundle_type=bundle_type,
                user_id=user_id,
                folder_id=folder_id,
                bundle_id=bundle_id,
            )
            await self._build_artifacts(
                db,
                bundle_id=bundle_id,
                bundle_type=bundle_type,
                source_path=source_path,
                user_id=user_id,
            )
            if project_id:
                await self._add_bundle_to_project(
                    db, project_id=project_id, bundle_id=bundle_id, imported=imported
                )
            return BundleImportResult(
                bundle_id=bundle_id, bundle_type=type_value, layers=imported
            )
        finally:
            await pool.close()
            self.cleanup()

    async def ingest_into_package(
        self,
        *,
        bundle_id: str,
        source_path: str,
        bundle_type: "BundleTypeName | str",
        user_id: str,
        folder_id: str,
        project_id: Optional[str] = None,
    ) -> BundleImportResult:
        """Ingest a validated source into an ALREADY-CREATED bundle (member
        layers), then flip the bundle's terminal status.

        When ``project_id`` is given (upload from within a project), the bundle
        is also added to that project as a locked bundle-backed group.

        This runs as the Windmill job kicked off by core's import endpoint (core
        created the shell as ``processing``). Because the job completes
        disconnected from any core request, the terminal status transition
        (``ready``/``failed``) is written here."""
        assert self.settings is not None, "init_from_env()/init() must run first"

        type_value = BundleTypeName(bundle_type).value
        pool = await self.get_postgres_pool()
        db = ToolDatabaseService(pool, schema=self.settings.customer_schema)
        try:
            try:
                imported = await self._ingest_layers(
                    db,
                    source_path=source_path,
                    bundle_type=bundle_type,
                    user_id=user_id,
                    folder_id=folder_id,
                    bundle_id=bundle_id,
                )
                # Artifacts gate readiness: the bundle stays "processing" until
                # its derived artifacts (e.g. the routing .bin) are built.
                await self._build_artifacts(
                    db,
                    bundle_id=bundle_id,
                    bundle_type=bundle_type,
                    source_path=source_path,
                    user_id=user_id,
                )
            except Exception:
                await db.update_package_status(
                    bundle_id=bundle_id, status=BundleStatus.failed
                )
                raise
            await db.update_package_status(
                bundle_id=bundle_id, status=BundleStatus.ready
            )
            # Add to the originating project (best-effort: the bundle is a valid,
            # ready import even if the project association fails).
            if project_id:
                try:
                    await self._add_bundle_to_project(
                        db,
                        project_id=project_id,
                        bundle_id=bundle_id,
                        imported=imported,
                    )
                except Exception:
                    logger.exception(
                        "Bundle %s imported but could not be added to project %s",
                        bundle_id,
                        project_id,
                    )
            return BundleImportResult(
                bundle_id=bundle_id, bundle_type=type_value, layers=imported
            )
        finally:
            await pool.close()
            self.cleanup()


async def import_bundle(
    *,
    source_path: str,
    bundle_type: "BundleTypeName | str",
    user_id: str,
    folder_id: str,
    name: str,
    description: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    bundle_id: Optional[str] = None,
) -> BundleImportResult:
    """Convenience entry point: build a runner from the environment and import."""
    runner = BundleImportRunner()
    runner.init_from_env()
    return await runner.run_import(
        source_path=source_path,
        bundle_type=bundle_type,
        user_id=user_id,
        folder_id=folder_id,
        name=name,
        description=description,
        properties=properties,
        bundle_id=bundle_id,
    )
