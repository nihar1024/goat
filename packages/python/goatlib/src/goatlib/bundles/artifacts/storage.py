"""Where a bundle's built artifacts live on disk.

Artifacts sit on the data volume next to DuckLake and tiles rather than in
object storage: the routing engine opens them as local files, so a round trip
through S3 would only be a download to the same volume.

Layout, relative to ``bundles_data_dir``::

    {bundle_id}/{kind}{suffix}     e.g. 3fa85f64-…/pt_network_graph.bin

The stored path is relative so the mount point can move between deployments
without rewriting rows. It is keyed by bundle rather than by user because a
bundle can be shared and rebuilt by someone other than its importer.
"""

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def artifact_relative_path(bundle_id: str, kind: str, suffix: str) -> str:
    return f"{bundle_id}/{kind}{suffix}"


def store_artifact(
    local_path: str,
    *,
    bundles_data_dir: str,
    bundle_id: str,
    kind: str,
    suffix: str,
) -> str:
    """Move a freshly built artifact into place, returning its relative path.

    The copy lands on a temporary name in the destination directory and is then
    renamed, so a reader never observes a half-written artifact and a rebuild
    replaces the previous one atomically.
    """
    relative = artifact_relative_path(bundle_id, kind, suffix)
    destination = Path(bundles_data_dir) / relative
    destination.parent.mkdir(parents=True, exist_ok=True)

    staging = destination.with_name(f".{destination.name}.incoming")
    try:
        shutil.copyfile(local_path, staging)
        os.replace(staging, destination)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return relative


def resolve_artifact(bundles_data_dir: str, storage_path: str) -> Optional[Path]:
    """The absolute path of a stored artifact, or None if the file is gone.

    A row can outlive its file (a volume restored from a backup that predates
    the build), and artifacts are regenerable, so a caller is told "absent"
    rather than handed a path that fails to open.
    """
    resolved = Path(bundles_data_dir) / storage_path
    if not resolved.is_file():
        logger.warning("Artifact row points at missing file %s", resolved)
        return None
    return resolved


def delete_bundle_artifacts(bundles_data_dir: str, bundle_id: str) -> int:
    """Remove every artifact of a bundle. Returns the number of files removed."""
    # The id names a directory to rmtree on a volume shared with other data —
    # anything that isn't a UUID (e.g. "../ducklake") must not reach the join.
    uuid.UUID(bundle_id)
    directory = Path(bundles_data_dir) / bundle_id
    if not directory.is_dir():
        return 0
    removed = sum(1 for entry in directory.iterdir() if entry.is_file())
    shutil.rmtree(directory)
    return removed
