"""Generic bundle import framework.

An importer turns an uploaded source (a GTFS zip, an OSM extract, …) into a set
of member layers for a bundle of a given type. The framework is
spec-driven: which roles are required comes from
``goatlib.models.bundle.SPECS``; how a source maps onto those roles is
the per-type importer's job. Register one importer per
``BundleTypeName`` and the runner/endpoints stay type-agnostic.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

from goatlib.models.bundle import (
    BundleTypeName,
    BundleTypeSpec,
    get_spec,
)

LayerKind = Literal["feature", "table"]
GeometryType = Literal["point", "line", "polygon"]


class ExtractedLayer(BaseModel):
    """One member layer produced from the source, ready to be ingested."""

    role: str
    name: str
    layer_type: LayerKind
    geometry_type: Optional[GeometryType] = None
    # Local file the runner hands to IOConverter → DuckLake (GeoJSON for
    # geometry roles, CSV for attribute tables).
    file_path: str


class ValidationResult(BaseModel):
    """Outcome of validating a source against a bundle type's spec."""

    valid: bool
    detected_roles: List[str] = []
    missing_required_roles: List[str] = []
    errors: List[str] = []


class BundleImporter(ABC):
    """Base class for per-type importers."""

    #: The bundle type this importer handles.
    bundle_type: BundleTypeName

    @property
    def spec(self) -> BundleTypeSpec:
        return get_spec(self.bundle_type)

    @abstractmethod
    def validate(self, source_path: str) -> ValidationResult:
        """Cheaply check the source against the type's spec (required roles
        present, key columns) — no full extraction. Safe to call synchronously."""

    @abstractmethod
    def extract_layers(self, source_path: str, workdir: str) -> List[ExtractedLayer]:
        """Produce the member layers' local files under ``workdir``. Assumes the
        source already validated."""


_REGISTRY: Dict[BundleTypeName, BundleImporter] = {}


def register_importer(importer: BundleImporter) -> BundleImporter:
    _REGISTRY[importer.bundle_type] = importer
    return importer


def get_importer(
    bundle_type: "BundleTypeName | str",
) -> BundleImporter:
    """Return the importer for a bundle type (raises if none registered)."""
    key = BundleTypeName(bundle_type)
    if key not in _REGISTRY:
        raise ValueError(
            f"No importer registered for bundle type '{key.value}'"
        )
    return _REGISTRY[key]
