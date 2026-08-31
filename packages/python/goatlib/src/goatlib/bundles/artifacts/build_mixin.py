"""Building and storing a bundle's derived artifacts.

Shared by the import runner and the rebuild tool: an import builds artifacts
once from a fresh source, and a rebuild builds them again after someone edited a
member layer. Both read the same layers and write the same files, so the logic
lives here rather than in either caller.

``built_revision`` is what separates the two. A rebuild passes the bundle's
``layers_revision`` as it was when the build started, and publishes only if that
is still current — a save landing mid-build queues its own rebuild, so this
one's output is already out of date. An import passes ``None``: nothing can have
superseded a bundle that did not exist yet.
"""

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from goatlib.bundles.artifacts import (
    ArtifactBuilderUnavailableError,
    get_artifact_builder,
    store_artifact,
)
from goatlib.models.bundle import BundleTypeName, get_spec
from goatlib.tools.db import ToolDatabaseService

logger = logging.getLogger(__name__)


class BundleArtifactBuildMixin:
    """Export member layers and build the bundle type's artifacts from them.

    Mixed into a tool runner, and it uses three things the runner provides:
    ``settings``, ``duckdb_con`` and ``get_layer_table_path``. Declared here so
    the requirement is visible rather than only failing at runtime on a host
    that lacks them.
    """

    if TYPE_CHECKING:
        settings: Any
        duckdb_con: Any

        def get_layer_table_path(self, layer_id: str) -> str: ...

    def export_member_layers(
        self, *, user_id: str, members: List[Dict], workdir: str
    ) -> Dict[str, str]:
        """Role -> local parquet path for each member layer.

        Reads back out of DuckLake rather than reusing the files an importer
        wrote, so the import path exercises the same code a rebuild-after-edit
        does, and an edited layer is what gets built.

        Copies the table directly rather than going through
        ``export_layer_to_parquet``: that resolves the layer's owner with a
        nested ``run_until_complete``, which cannot work inside an already
        running event loop, and none of its filtering applies here. The owner
        is known from the bundle.
        """
        if not members:
            raise ValueError(
                "Cannot build a layer-based artifact without the member layers"
            )
        paths: Dict[str, str] = {}
        for member in members:
            role = member["role"]
            table = self.get_layer_table_path(str(member["layer_id"]))
            out = Path(workdir) / f"{role}.parquet"
            self.duckdb_con.execute(
                f"COPY (SELECT * FROM {table}) TO '{out}' (FORMAT PARQUET)"
            )
            paths[role] = str(out)
        logger.info("Exported %d member layer(s) for artifact build", len(paths))
        return paths

    async def build_and_store_artifacts(
        self,
        db: ToolDatabaseService,
        *,
        bundle_id: str,
        bundle_type: "BundleTypeName | str",
        source_path: str,
        user_id: str,
        members: Optional[List[Dict]] = None,
        built_revision: Optional[int] = None,
    ) -> bool:
        """Build and store the bundle type's derived artifacts (per spec).

        Each artifact is written to a temp file, moved onto the data volume, and
        recorded as a ``bundle_artifact`` row (building → ready). A build failure
        propagates so the caller marks the bundle failed; a missing toolchain is
        skipped with a warning (the import still completes).

        Returns whether the artifacts were published. ``False`` means a later
        save superseded this build, which is not an error.
        """
        assert self.settings is not None
        spec = get_spec(bundle_type)
        builder = get_artifact_builder(bundle_type)
        if not spec.artifacts or builder is None:
            return True

        published = True
        with tempfile.TemporaryDirectory() as workdir:
            try:
                # A builder reads either the uploaded source (GTFS: the feed is
                # the truth) or the member layers (street networks: the layers
                # are, so an edited layer is what a rebuild must pick up).
                if builder.builds_from_layers:
                    layer_paths = self.export_member_layers(
                        user_id=user_id, members=members or [], workdir=workdir
                    )
                    built = builder.build_from_layers(
                        layer_paths=layer_paths, workdir=workdir
                    )
                else:
                    built = builder.build(source_path=source_path, workdir=workdir)
            except ArtifactBuilderUnavailableError as e:
                logger.warning(
                    "Skipping artifact build for bundle %s: %s", bundle_id, e
                )
                return True
            except Exception:
                # The build died before reaching any artifact row. Mark them
                # failed so consumers report "the last update failed — update
                # it from the bundle" instead of promising an update that is
                # not running. (On an import no rows exist yet, so this is a
                # no-op and the caller's bundle-failed handling takes over.)
                await db.mark_bundle_artifacts_failed(bundle_id)
                raise

            for art in built:
                kind_value = getattr(art.kind, "value", art.kind)
                artifact_id = await db.create_artifact(
                    bundle_id=bundle_id, kind=kind_value, status="building"
                )
                try:
                    # Keep the built file's extension: a PT timetable is a
                    # .bin, a street network graph is a .tar of two parquet
                    # files, and the consumer dispatches on it.
                    suffix = Path(art.local_path).suffix or ".bin"
                    storage_path = store_artifact(
                        art.local_path,
                        bundles_data_dir=self.settings.bundles_data_dir,
                        bundle_id=bundle_id,
                        kind=kind_value,
                        suffix=suffix,
                    )
                    if built_revision is None:
                        await db.update_artifact_status(
                            artifact_id=artifact_id,
                            status="ready",
                            storage_path=storage_path,
                            size=art.size,
                        )
                    else:
                        current = await db.publish_artifact_if_current(
                            artifact_id=artifact_id,
                            bundle_id=bundle_id,
                            built_revision=built_revision,
                            storage_path=storage_path,
                            size=art.size,
                        )
                        if not current:
                            # A save landed while this built. Leave it stale for
                            # the rebuild that save queued.
                            published = False
                            await db.update_artifact_status(
                                artifact_id=artifact_id, status="stale"
                            )
                            logger.info(
                                "Discarding superseded %s build for bundle %s "
                                "(built from revision %d)",
                                kind_value,
                                bundle_id,
                                built_revision,
                            )
                            continue
                    logger.info(
                        "Artifact %s for bundle %s stored at %s (%d bytes)",
                        kind_value,
                        bundle_id,
                        storage_path,
                        art.size,
                    )
                except Exception:
                    await db.update_artifact_status(
                        artifact_id=artifact_id, status="failed"
                    )
                    raise

        return published
