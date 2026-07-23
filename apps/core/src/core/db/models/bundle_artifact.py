"""
Bundle Artifact Model
"""

from typing import TYPE_CHECKING
from uuid import UUID

from goatlib.models.bundle import (
    BundleArtifactKind,
    BundleArtifactStatus,
)
from pydantic import field_serializer
from sqlalchemy import ForeignKey, Text
from sqlalchemy import Integer as SAInteger
from sqlalchemy.dialects.postgresql import UUID as UUID_PG
from sqlmodel import Column, Field, Relationship, UniqueConstraint, text

from core.core.config import settings
from core.db.models._base_class import DateTimeBase, serialize_str_enum

if TYPE_CHECKING:
    from .bundle import Bundle


class BundleArtifact(DateTimeBase, table=True):
    """A derived, regenerable artifact of a bundle (e.g. the routable
    graph ``.bin`` or a stop-to-street mapping).

    The artifact is not a layer — it is a build product stored in object storage
    (``s3_key``) and rebuilt on demand. At most one artifact per
    ``(bundle_id, kind)``.
    """

    __tablename__ = "bundle_artifact"
    __table_args__ = (
        UniqueConstraint(
            "bundle_id", "kind", name="uq_bundle_artifact_kind"
        ),
        {"schema": settings.SCHEMA},
    )

    id: UUID | None = Field(
        default=None,
        sa_column=Column(
            UUID_PG(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("uuid_generate_v4()"),
        ),
        description="Artifact ID",
    )
    bundle_id: UUID = Field(
        sa_column=Column(
            UUID_PG(as_uuid=True),
            ForeignKey(f"{settings.SCHEMA}.bundle.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        description="Bundle this artifact was derived from",
    )
    kind: BundleArtifactKind = Field(
        sa_column=Column(Text, nullable=False),
        description="Artifact kind (e.g. pt_network_graph, pt_network_linkage)",
    )
    status: BundleArtifactStatus = Field(
        default=BundleArtifactStatus.pending,
        sa_column=Column(
            Text, nullable=False, server_default=BundleArtifactStatus.pending
        ),
        description="Build state of the artifact",
    )
    s3_key: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Object-storage key of the built artifact (null until built)",
    )
    size: int | None = Field(
        default=None,
        sa_column=Column(SAInteger, nullable=True),
        description="Size of the artifact in bytes",
    )
    job_id: UUID | None = Field(
        default=None,
        sa_column=Column(UUID_PG(as_uuid=True), nullable=True),
        description="Windmill job ID of the build that produced this artifact",
    )

    # Relationships
    bundle: "Bundle" = Relationship(back_populates="artifacts")

    @field_serializer("kind", "status")
    def serialize_enums(self, value: object) -> "str | None":
        return serialize_str_enum(value)
