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
from goatlib.bundles.artifacts.street_network import StreetNetworkArtifactBuilder

register_artifact_builder(GtfsArtifactBuilder())
register_artifact_builder(StreetNetworkArtifactBuilder())

__all__ = [
    "ArtifactBuilder",
    "ArtifactBuilderUnavailableError",
    "BuiltArtifact",
    "GtfsArtifactBuilder",
    "StreetNetworkArtifactBuilder",
    "get_artifact_builder",
    "register_artifact_builder",
]
