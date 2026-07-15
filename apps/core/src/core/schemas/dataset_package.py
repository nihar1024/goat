from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.db.models.dataset_package_type import DatasetPackageTypeName


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
    properties: Dict[str, Any] | None = Field(
        None, description="Dataset-level metadata conforming to the type's structure"
    )


class DatasetPackageRead(DatasetPackageBase):
    id: UUID = Field(..., description="Dataset package ID")
    user_id: UUID = Field(..., description="Dataset package owner ID")
    folder_id: UUID = Field(..., description="Folder the package lives in")
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
