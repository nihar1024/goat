"""
Dataset Package Model
"""

from typing import TYPE_CHECKING, Any, Dict, List
from uuid import UUID

from goatlib.models.dataset_package import DatasetPackageStatus
from pydantic import field_serializer
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as UUID_PG
from sqlmodel import Column, Field, Relationship, text

from core.core.config import settings
from core.db.models._base_class import (
    ContentBaseAttributes,
    DateTimeBase,
    serialize_str_enum,
)
from core.db.models.dataset_package_type import DatasetPackageTypeName

if TYPE_CHECKING:
    from ._link_model import DatasetPackageDependencyLink, DatasetPackageLayerLink
    from .dataset_package_artifact import DatasetPackageArtifact
    from .dataset_package_type import DatasetPackageType
    from .folder import Folder
    from .user import User


class DatasetPackage(ContentBaseAttributes, DateTimeBase, table=True):
    """A group of layers that form a single dataset and must be managed together.

    Datasets such as a street network (nodes + edges) or a GTFS public-transport
    feed (stops, routes, trips, …) are made up of several layers that only make
    sense as a unit. A dataset package bundles those member layers under one
    owner and folder, tagged with a ``dataset_package_type`` whose ``structure``
    describes the expected roles/artifacts. Deleting a package cascades to its
    layers.

    Inherits ``folder_id``, ``name`` and ``description`` from
    ``ContentBaseAttributes`` and ``created_at``/``updated_at`` from
    ``DateTimeBase``.
    """

    __tablename__ = "dataset_package"
    __table_args__ = {"schema": settings.SCHEMA}

    id: UUID | None = Field(
        default=None,
        sa_column=Column(
            UUID_PG(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("uuid_generate_v4()"),
        ),
        description="Dataset package ID",
    )
    user_id: UUID = Field(
        sa_column=Column(
            UUID_PG(as_uuid=True),
            ForeignKey(f"{settings.SCHEMA}.user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        description="Dataset package owner ID",
    )
    dataset_package_type: DatasetPackageTypeName = Field(
        sa_column=Column(
            Text,
            ForeignKey(
                f"{settings.SCHEMA}.dataset_package_type.type", ondelete="RESTRICT"
            ),
            nullable=False,
            index=True,
        ),
        description="Dataset package type (FK to dataset_package_type.type)",
    )
    properties: Dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="Dataset-level metadata conforming to the type's structure",
    )
    status: DatasetPackageStatus = Field(
        default=DatasetPackageStatus.ready,
        sa_column=Column(
            Text, nullable=False, server_default=DatasetPackageStatus.ready
        ),
        description="Processing lifecycle status (import sets processing → ready/failed)",
    )

    # Relationships
    user: "User" = Relationship(back_populates="dataset_packages")
    folder: "Folder" = Relationship(back_populates="dataset_packages")
    type_definition: "DatasetPackageType" = Relationship(back_populates="packages")
    layer_links: List["DatasetPackageLayerLink"] = Relationship(
        back_populates="dataset_package",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    artifacts: List["DatasetPackageArtifact"] = Relationship(
        back_populates="dataset_package",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    # Dependencies this package declares on other packages (e.g. GTFS -> street).
    dependency_links: List["DatasetPackageDependencyLink"] = Relationship(
        back_populates="dataset_package",
        sa_relationship_kwargs={
            "foreign_keys": "[DatasetPackageDependencyLink.dataset_package_id]",
            "cascade": "all, delete-orphan",
        },
    )
    # Dependencies other packages declare on this one (e.g. GTFS packages that
    # use this street network). passive_deletes lets the DB ON DELETE CASCADE
    # drop these rows instead of the ORM nullifying their (NOT NULL) FK.
    dependent_links: List["DatasetPackageDependencyLink"] = Relationship(
        back_populates="depends_on_package",
        sa_relationship_kwargs={
            "foreign_keys": "[DatasetPackageDependencyLink.depends_on_package_id]",
            "passive_deletes": True,
        },
    )

    @field_serializer("dataset_package_type", "status")
    def serialize_enums(self, value: object) -> "str | None":
        return serialize_str_enum(value)
