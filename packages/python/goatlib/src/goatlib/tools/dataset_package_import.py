"""Windmill entrypoint for dataset package import.

Ingests an uploaded source (e.g. a GTFS zip) into an already-created dataset
package: downloads it from object storage, then runs the goatlib
``DatasetPackageImportRunner`` to create the member layers and flip the package
status to ready/failed. Core creates the package shell (status=processing) and
triggers this job via the processes service.
"""

import os
import tempfile
from typing import Any, Dict

from pydantic import Field

from goatlib.dataset_packages.runner import DatasetPackageImportRunner
from goatlib.tools.base import _get_or_create_event_loop
from goatlib.tools.schemas import ToolInputBase


class DatasetPackageImportParams(ToolInputBase):
    """Inputs for the dataset package import tool. ``user_id`` and ``folder_id``
    are inherited from ``ToolInputBase``."""

    package_id: str = Field(
        ..., description="Pre-created dataset package id to ingest layers into"
    )
    s3_key: str = Field(
        ..., description="Object-storage key of the uploaded source (e.g. gtfs.zip)"
    )
    dataset_package_type: str = Field(
        ..., description="Dataset package type (e.g. pt_network_gtfs)"
    )


def main(params: DatasetPackageImportParams) -> Dict[str, Any]:
    """Windmill entry point for the dataset package import tool."""
    if not params.folder_id:
        raise ValueError("folder_id is required for dataset package import")

    runner = DatasetPackageImportRunner()
    runner.init_from_env()
    assert runner.settings is not None

    tmp_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
    try:
        runner.settings.get_s3_client().download_file(
            runner.settings.s3_bucket_name, params.s3_key, tmp_path
        )
        result = _get_or_create_event_loop().run_until_complete(
            runner.ingest_into_package(
                package_id=params.package_id,
                source_path=tmp_path,
                dataset_package_type=params.dataset_package_type,
                user_id=params.user_id,
                folder_id=params.folder_id,
            )
        )
        return result.model_dump()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        runner.cleanup()
