"""Artifact builders for dataset bundles.

Spec-driven, mirroring importers: which artifacts a bundle type produces comes
from ``goatlib.models.bundle.SPECS``; how to build each is per-type here.

Boundary: a builder turns the bundle source into artifact file(s) on disk. The
runner stores them (S3 + ``bundle_artifact`` rows). Builders never touch the DB.
"""

from abc import ABC, abstractmethod
from typing import List

from pydantic import BaseModel

from goatlib.models.bundle import BundleArtifactKind, BundleTypeName


class ArtifactBuilderUnavailableError(Exception):
    """Raised when a builder's toolchain isn't available in this environment
    (e.g. the routing extension hasn't been rebuilt with the timetable-build
    binding yet). The import still completes; the artifact is skipped."""


class BuiltArtifact(BaseModel):
    """A produced artifact file, ready to be stored by the runner."""

    kind: BundleArtifactKind
    local_path: str
    size: int


class ArtifactBuilder(ABC):
    """Builds a bundle type's derived artifacts from its source."""

    bundle_type: BundleTypeName
    # The artifact kinds this builder currently produces (may be a subset of the
    # type spec's declared artifacts while others are still unimplemented).
    produces: tuple[BundleArtifactKind, ...] = ()

    @abstractmethod
    def build(self, *, source_path: str, workdir: str) -> List[BuiltArtifact]:
        """Build the artifacts from ``source_path`` into ``workdir``.

        Raises ``ArtifactBuilderUnavailableError`` if the toolchain is missing.
        """
