from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class FolderBase(BaseModel):
    name: str = Field(..., description="Folder name", max_length=255)


class FolderCreate(FolderBase):
    user_id: UUID | None = Field(None, description="Folder owner ID")


class FolderUpdate(FolderBase):
    pass


class FolderRead(FolderBase):
    id: UUID = Field(..., description="Folder ID")
    user_id: UUID = Field(..., description="Folder owner ID")
    is_owned: bool = Field(True, description="False when this folder is shared to the requesting user")
    role: str | None = Field(None, description="Effective role: folder-owner | folder-viewer | folder-editor")
    shared_from_name: str | None = Field(None, description="Team or organization name the folder was shared through")
    shared_with_ids: list[UUID] | None = Field(None, description="Team/org IDs this owned folder has been shared with")


class FolderShareCreate(BaseModel):
    grantee_type: Literal["team", "organization"]
    grantee_id: UUID
    role: Literal["folder-viewer", "folder-editor"]


class FolderGrantResponse(BaseModel):
    grantee_type: str
    grantee_id: UUID
    grantee_name: str
    role: str


class FolderGrantsResponse(BaseModel):
    grants: list[FolderGrantResponse]


# Body of request examples

request_examples = {
    "create": {
        "name": "First folder",
    },
    "update": {
        "name": "Better folder name",
    },
}
