from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.db.models.dataset_package_type import DatasetPackageTypeName
from core.schemas.layer import ThumbnailUrlMixin


class DatasetPackageBase(BaseModel):
    name: str = Field(..., description="Dataset package name", max_length=255)
    description: str | None = Field(
        None, description="Dataset package description", max_length=2000
    )
    dataset_package_type: DatasetPackageTypeName = Field(
        ..., description="Dataset package type"
    )
    properties: Dict[str, Any] | None = Field(
        None, description="Dataset-level metadata conforming to the type's structure"
    )


class DatasetPackageCreate(DatasetPackageBase):
    folder_id: UUID = Field(..., description="Folder the package lives in")
    user_id: UUID | None = Field(None, description="Dataset package owner ID")


class DatasetPackageUpdate(BaseModel):
    name: str | None = Field(None, description="Dataset package name", max_length=255)
    description: str | None = Field(
        None, description="Dataset package description", max_length=2000
    )
    folder_id: UUID | None = Field(
        None,
        description="Move the dataset package (and its member layers) to this folder",
    )
    properties: Dict[str, Any] | None = Field(
        None, description="Dataset-level metadata conforming to the type's structure"
    )


class DatasetContentTile(ThumbnailUrlMixin):
    """One item in the dataset content grid — a layer OR a dataset package,
    projected to a single uniform shape so the mixed listing returns one
    consistent DTO for both (rather than rich layer DTOs next to package tiles).

    ``content_type`` discriminates the two; ``type`` is the layer type or the
    package type, so the tile chip resolves the same way for both.
    """

    content_type: Literal["layer", "dataset_package"]
    id: UUID
    name: Optional[str] = None
    folder_id: Optional[UUID] = None
    type: Optional[str] = Field(
        None, description="Layer type or dataset package type"
    )
    feature_layer_geometry_type: Optional[str] = Field(
        None, description="Geometry type for feature layers (null for packages)"
    )
    data_type: Optional[str] = None
    dataset_package_type: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = Field(None, validate_default=True)
    owned_by: Dict[str, Any] | None = None
    shared_with: Dict[str, Any] | None = None
    tags: Optional[list[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DatasetPackageRead(DatasetPackageBase, ThumbnailUrlMixin):
    id: UUID = Field(..., description="Dataset package ID")
    user_id: UUID = Field(..., description="Dataset package owner ID")
    folder_id: UUID = Field(..., description="Folder the package lives in")
    status: str = Field("ready", description="Processing lifecycle status")
    # Packages have no thumbnail of their own yet; the mixin falls back to the
    # standard dataset image (same logic as layers). validate_default lets the
    # mixin's before-validator run even when no value is supplied.
    thumbnail_url: Optional[str] = Field(
        None, description="Thumbnail URL", validate_default=True
    )
    owned_by: Dict[str, Any] | None = Field(
        None, description="Owner info ({id, firstname, lastname, avatar}) for tiles"
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Sharing ---------------------------------------------------------------


class DatasetPackageShareCreate(BaseModel):
    grantee_type: Literal["team", "organization"]
    grantee_id: UUID
    role: Literal["dataset-package-viewer", "dataset-package-editor"]


class DatasetPackageGrantResponse(BaseModel):
    grantee_type: str
    grantee_id: UUID
    grantee_name: str
    role: str


class DatasetPackageGrantsResponse(BaseModel):
    grants: list[DatasetPackageGrantResponse]


# --- Import ----------------------------------------------------------------


class DatasetPackageImportRequest(BaseModel):
    s3_key: str = Field(
        ..., description="Object-storage key of the uploaded source (e.g. a gtfs.zip)"
    )
    folder_id: UUID = Field(..., description="Folder to create the package in")
    name: str = Field(..., description="Dataset package name", max_length=255)
    description: str | None = Field(None, max_length=2000)
    street_network_package_id: UUID | None = Field(
        None,
        description="Street network package to link as a dependency (PT networks)",
    )


class DatasetPackageImportResponse(BaseModel):
    package: "DatasetPackageRead"
    job_id: str | None = Field(
        None, description="Windmill job id for the background ingest (poll for status)"
    )


# --- Dependencies ----------------------------------------------------------


class DatasetPackageDependencyCreate(BaseModel):
    depends_on_package_id: UUID = Field(
        ..., description="The package this one depends on (e.g. a street network)"
    )
    dependency_kind: str = Field(
        ..., description="Dependency slot from the type spec (e.g. 'street_network')"
    )


class DatasetPackageDependencyResponse(BaseModel):
    dependency_kind: str
    depends_on_package_id: UUID
    depends_on_name: str
    depends_on_type: str


# --- Membership ------------------------------------------------------------


class DatasetPackageMemberCreate(BaseModel):
    layer_id: UUID = Field(..., description="Layer to add to the package")
    role: str | None = Field(
        None, description="Role the layer plays in the package (a spec role key)"
    )


class DatasetPackageMemberResponse(BaseModel):
    layer_id: UUID
    role: str | None


request_examples = {
    "create": {
        "name": "Munich GTFS feed",
        "dataset_package_type": "pt_network_gtfs",
        "folder_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "properties": {"layers": {}},
    },
}
