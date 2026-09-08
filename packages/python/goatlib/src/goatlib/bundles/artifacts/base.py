"""Artifact builders for dataset bundles.

Spec-driven, mirroring importers: which artifacts a bundle type produces comes
from ``goatlib.models.bundle.SPECS``; how to build each is per-type here.

Boundary: a builder turns the bundle source into artifact file(s) on disk. The
runner stores them (S3 + ``bundle_artifact`` rows). Builders never touch the DB.
"""

from abc import ABC
from typing import Dict, List, Protocol, Tuple

from pydantic import BaseModel

from goatlib.models.bundle import (
    BundleArtifactKind,
    BundleArtifactState,
    BundleTypeName,
    get_spec,
)


class ArtifactSource(Protocol):
    """The one capability the ``fetch_*`` helpers need of a tool runner.

    A Protocol rather than ``BaseToolRunner`` keeps the dependency pointing from
    tools to bundles: ``bundles.runner`` already imports ``tools``, so importing
    it back would close a cycle.
    """

    def resolve_bundle_artifact(
        self, bundle_id: str, kind: str
    ) -> Tuple[str | None, BundleArtifactState | None]: ...


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

    @property
    def builds_from_layers(self) -> bool:
        """True when the build reads the bundle's member layers instead of the
        uploaded source.

        Read from the type spec rather than declared per builder: the API has to
        answer the same question (to know whether a filtered copy is possible)
        and cannot import a builder to ask — one of them pulls in DuckDB and the
        routing extension.
        """
        return get_spec(self.bundle_type).artifacts_build_from_layers

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
