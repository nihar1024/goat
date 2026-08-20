"""Artifact builders for dataset bundles.

Spec-driven, mirroring importers: which artifacts a bundle type produces comes
from ``goatlib.models.bundle.SPECS``; how to build each is per-type here.

Boundary: a builder turns the bundle source into artifact file(s) on disk. The
runner stores them (S3 + ``bundle_artifact`` rows). Builders never touch the DB.
"""

from abc import ABC
from typing import Dict, List

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
    """Builds a bundle type's derived artifacts."""

    bundle_type: BundleTypeName
    # The artifact kinds this builder currently produces (may be a subset of the
    # type spec's declared artifacts while others are still unimplemented).
    produces: tuple[BundleArtifactKind, ...] = ()
    # True when the build reads the bundle's member layers instead of the
    # uploaded source. Layers are the source of truth for types whose members can
    # be edited, so their artifact must be rebuildable from the edited layer
    # rather than from the original upload.
    builds_from_layers: bool = False

    def build(self, *, source_path: str, workdir: str) -> List[BuiltArtifact]:
        """Build the artifacts from ``source_path`` into ``workdir``.

        Raises ``ArtifactBuilderUnavailableError`` if the toolchain is missing.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not build from a source file"
        )

    def build_from_layers(
        self, *, layer_paths: Dict[str, str], workdir: str
    ) -> List[BuiltArtifact]:
        """Build the artifacts from member layers, keyed by spec role."""
        raise NotImplementedError(
            f"{type(self).__name__} does not build from member layers"
        )
