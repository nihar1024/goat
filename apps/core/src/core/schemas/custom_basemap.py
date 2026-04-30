from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator


class _BaseCustomBasemap(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    thumbnail_url: str | None = Field(default=None, max_length=2048)
    created_at: datetime
    updated_at: datetime


class VectorCustomBasemap(_BaseCustomBasemap):
    type: Literal["vector"] = "vector"
    url: HttpUrl


class RasterCustomBasemap(_BaseCustomBasemap):
    type: Literal["raster"] = "raster"
    url: str = Field(max_length=2048)
    attribution: str | None = Field(default=None, max_length=500)

    @field_validator("url")
    @classmethod
    def must_have_xyz_placeholders(cls, value: str) -> str:
        if "{z}" not in value or "{x}" not in value or "{y}" not in value:
            raise ValueError("Raster URL must contain {z}, {x}, and {y} placeholders")
        return value


class SolidCustomBasemap(_BaseCustomBasemap):
    type: Literal["solid"] = "solid"
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")


CustomBasemap = Annotated[
    VectorCustomBasemap | RasterCustomBasemap | SolidCustomBasemap,
    Field(discriminator="type"),
]
