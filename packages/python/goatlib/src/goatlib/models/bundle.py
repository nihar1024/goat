"""Bundle type specifications.

Code is the source of truth for the set of bundle types, the member
layer roles each one expects, the derived artifacts it produces, and the other
bundles it depends on. Core projects these specs into the
``bundle_type`` table's ``structure`` column (via
``seed_bundle_types``) and validates against them.
"""

from enum import Enum
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel

GeometryKind = Literal["point", "line", "polygon", "none"]


class BundleTypeName(str, Enum):
    """Supported bundle types (the vocabulary shared across services)."""

    street_network = "street_network"
    pt_network_gtfs = "pt_network_gtfs"


class BundleArtifactKind(str, Enum):
    """Derived artifacts a bundle can produce (e.g. a routable graph)."""

    pt_network_graph = "pt_network_graph"
    pt_network_linkage = "pt_network_linkage"
    # Produced by street_network bundles (builder added down the line).
    street_network_graph = "street_network_graph"


class BundleArtifactStatus(str, Enum):
    """Build state of a derived artifact."""

    pending = "pending"
    building = "building"
    ready = "ready"
    stale = "stale"
    failed = "failed"


class BundleStatus(str, Enum):
    """Processing lifecycle of a bundle (e.g. during import)."""

    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class RoleSpec(BaseModel):
    """A member-layer role within a bundle type."""

    key: str
    label: str
    required: bool = False
    # Expected geometry of the member layer for this role; "none" = attribute
    # table (no geometry); None = unconstrained.
    geometry: Optional[GeometryKind] = None
    # Columns the member layer must expose for downstream tools (native names).
    required_columns: Tuple[str, ...] = ()
    description: Optional[str] = None


class DependencySpec(BaseModel):
    """A dependency of one bundle on another.

    e.g. a GTFS bundle depends on a street network bundle to build its routable
    graph and stop-to-street mapping.
    """

    kind: str  # slot identifier, e.g. "street_network"
    bundle_type: BundleTypeName  # required type of the linked bundle
    required: bool = False
    description: Optional[str] = None


class BundleTypeSpec(BaseModel):
    """Structure of a bundle type: member roles, derived artifacts, and
    dependencies on other bundles."""

    type: BundleTypeName
    name: str
    description: str
    roles: Tuple[RoleSpec, ...]
    artifacts: Tuple[BundleArtifactKind, ...] = ()
    dependencies: Tuple[DependencySpec, ...] = ()

    def role(self, key: str) -> Optional[RoleSpec]:
        return next((r for r in self.roles if r.key == key), None)

    def role_keys(self) -> Tuple[str, ...]:
        return tuple(r.key for r in self.roles)

    def required_role_keys(self) -> Tuple[str, ...]:
        return tuple(r.key for r in self.roles if r.required)

    def dependency(self, kind: str) -> Optional[DependencySpec]:
        return next((d for d in self.dependencies if d.kind == kind), None)

    def to_structure(self) -> Dict[str, Any]:
        """Descriptive projection of the type for the ``bundle_type``
        table / frontend. Describes the roles, artifacts and dependencies —
        membership itself lives in the ``bundle_layer`` link table."""
        return {
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "roles": [
                {
                    "key": r.key,
                    "label": r.label,
                    "required": r.required,
                    "geometry": r.geometry,
                    "required_columns": list(r.required_columns),
                    "description": r.description,
                }
                for r in self.roles
            ],
            "artifacts": [k.value for k in self.artifacts],
            "dependencies": [
                {
                    "kind": d.kind,
                    "bundle_type": d.bundle_type.value,
                    "required": d.required,
                    "description": d.description,
                }
                for d in self.dependencies
            ],
        }


SPECS: Dict[BundleTypeName, BundleTypeSpec] = {
    BundleTypeName.street_network: BundleTypeSpec(
        type=BundleTypeName.street_network,
        name="Street Network",
        description=(
            "A routable street network made up of edge segments and, optionally, "
            "the nodes they connect."
        ),
        roles=(
            RoleSpec(
                key="edges",
                label="Edges",
                required=True,
                geometry="line",
                description="Street segments (edges) of the network.",
            ),
            RoleSpec(
                key="nodes",
                label="Nodes",
                required=False,
                geometry="point",
                description="Network nodes connecting the edges.",
            ),
        ),
        artifacts=(BundleArtifactKind.street_network_graph,),
    ),
    BundleTypeName.pt_network_gtfs: BundleTypeSpec(
        type=BundleTypeName.pt_network_gtfs,
        name="Public Transport Network (GTFS)",
        description=(
            "A public-transport network imported from a GTFS feed. Member layers "
            "correspond to the GTFS files."
        ),
        roles=(
            RoleSpec(key="agency", label="Agency", geometry="none"),
            RoleSpec(key="stops", label="Stops", required=True, geometry="point"),
            RoleSpec(key="routes", label="Routes", required=True, geometry="none"),
            RoleSpec(key="trips", label="Trips", required=True, geometry="none"),
            RoleSpec(
                key="stop_times", label="Stop times", required=True, geometry="none"
            ),
            RoleSpec(key="calendar", label="Calendar", geometry="none"),
            RoleSpec(key="shapes", label="Shapes", geometry="line"),
        ),
        artifacts=(
            BundleArtifactKind.pt_network_graph,
            BundleArtifactKind.pt_network_linkage,
        ),
        dependencies=(
            DependencySpec(
                kind="street_network",
                bundle_type=BundleTypeName.street_network,
                required=True,
                description=(
                    "Street network used to build the routable graph and to map "
                    "stops onto the street network."
                ),
            ),
        ),
    ),
}


def get_spec(type_: "BundleTypeName | str") -> BundleTypeSpec:
    """Return the spec for a type name (raises KeyError/ValueError if unknown)."""
    return SPECS[BundleTypeName(type_)]
