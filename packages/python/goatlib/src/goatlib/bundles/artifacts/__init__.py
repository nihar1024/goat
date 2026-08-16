"""Dataset-bundle artifact builders. Importing this registers all builders."""

from goatlib.bundles.artifacts.base import (
    ArtifactBuilder,
    ArtifactBuilderUnavailableError,
    BuiltArtifact,
)
from goatlib.bundles.artifacts.gtfs import GtfsArtifactBuilder
from goatlib.bundles.artifacts.registry import (
    get_artifact_builder,
    register_artifact_builder,
)

register_artifact_builder(GtfsArtifactBuilder())

__all__ = [
    "ArtifactBuilder",
    "ArtifactBuilderUnavailableError",
    "BuiltArtifact",
    "GtfsArtifactBuilder",
    "get_artifact_builder",
    "register_artifact_builder",
]
