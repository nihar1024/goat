"""
Dataset Package Type Model
"""

from typing import TYPE_CHECKING, Any, Dict, List

from goatlib.models.dataset_package import DatasetPackageTypeName
from pydantic import field_serializer
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, Relationship, Text

from core.core.config import settings
from core.db.models._base_class import DateTimeBase, serialize_str_enum

if TYPE_CHECKING:
    from .dataset_package import DatasetPackage

# Re-exported for callers that import the vocabulary from the model module; the
# spec registry in goatlib is the source of truth.
__all__ = ["DatasetPackageType", "DatasetPackageTypeName"]


class DatasetPackageType(DateTimeBase, table=True):
    """Reference table describing a kind of dataset package.

    Holds the type identifier plus a ``structure`` projection (roles, derived
    artifacts and dependencies) generated from the goatlib spec. Seeded by
    ``seed_dataset_package_types`` and referenced by
    ``dataset_package.dataset_package_type``.
    """

    __tablename__ = "dataset_package_type"
    __table_args__ = {"schema": settings.SCHEMA}

    type: DatasetPackageTypeName = Field(
        sa_column=Column(Text, primary_key=True, nullable=False),
        description="Dataset package type identifier (natural primary key)",
    )
    name: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Human-readable dataset package type name",
        max_length=255,
    )
    description: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Dataset package type description",
    )
    structure: Dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False),
        description=(
            "Descriptive projection of the type's goatlib spec: its member roles, "
            "derived artifacts and package dependencies (membership itself lives "
            "in dataset_package_layer)"
        ),
    )

    # Relationships
    packages: List["DatasetPackage"] = Relationship(back_populates="type_definition")

    @field_serializer("type")
    def serialize_type(
        self, value: "DatasetPackageTypeName | str | None"
    ) -> "str | None":
        return serialize_str_enum(value)
