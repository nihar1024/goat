"""Where an edited edge's endpoint belongs: an existing node, a split, or a new node.

Every coordinate here is EPSG:3857 metres. The caller projects before asking and
writes 4326 geometry afterwards — a split is applied as a fraction along the
stored line, so the new vertex lands exactly on it whichever CRS it is stored in.

Ordering is fixed rather than incidental: node reuse beats splitting, and ties
break by id. Two saves of the same edits must produce the same topology, or a
rebuilt graph stops being reproducible.
"""

from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple, TypeVar, Union

from shapely.geometry import LineString, Point


class DegenerateEdgeError(ValueError):
    """An edge whose endpoints resolve to the same node."""


@dataclass(frozen=True)
class NodeCandidate:
    node_id: str
    x: float
    y: float

    @property
    def point(self) -> Point:
        return Point(self.x, self.y)


@dataclass(frozen=True)
class EdgeCandidate:
    edge_id: str
    source_node: str
    target_node: str
    geometry: LineString


@dataclass(frozen=True)
class ReuseNode:
    node_id: str


@dataclass(frozen=True)
class SplitEdge:
    edge_id: str
    fraction: float


@dataclass(frozen=True)
class MintNode:
    x: float
    y: float


Resolution = Union[ReuseNode, SplitEdge, MintNode]


def resolve_endpoint(
    point: Point,
    nodes: Sequence[NodeCandidate],
    edges: Sequence[EdgeCandidate],
    tolerance_m: float,
) -> Resolution:
    """Decide what an edge endpoint at ``point`` should connect to."""
    nearest_node = _nearest(
        [(node.point.distance(point), node.node_id, node) for node in nodes],
        tolerance_m,
    )
    if nearest_node is not None:
        return ReuseNode(nearest_node.node_id)

    candidates: list[Tuple[float, str, Tuple[EdgeCandidate, float]]] = []
    for edge in edges:
        # Length first: a zero-length line makes shapely's distance return NaN,
        # and a NaN comparison would decide this by accident.
        length = edge.geometry.length
        if length == 0:
            continue
        distance = edge.geometry.distance(point)
        if distance > tolerance_m:
            continue
        fraction = edge.geometry.project(point, normalized=True)
        # A hit near an edge's own end belongs to that end's node, which the
        # node pass above already had its chance at. Splitting there would mint
        # a second node on top of an existing one.
        margin = tolerance_m / length
        if fraction <= margin or fraction >= 1 - margin:
            continue
        candidates.append((distance, edge.edge_id, (edge, fraction)))

    nearest_edge = _nearest(candidates, tolerance_m)
    if nearest_edge is not None:
        edge, fraction = nearest_edge
        return SplitEdge(edge.edge_id, fraction)

    return MintNode(point.x, point.y)


T = TypeVar("T")


def _nearest(
    scored: Sequence[Tuple[float, str, T]], tolerance_m: float
) -> T | None:
    """Closest candidate within tolerance; ties break by id."""
    in_range = [item for item in scored if item[0] <= tolerance_m]
    if not in_range:
        return None
    return min(in_range, key=lambda item: (item[0], item[1]))[2]


def orphaned_nodes(
    candidate_ids: set[str], surviving_edges: Iterable[tuple[str, str]]
) -> set[str]:
    """Which of ``candidate_ids`` no surviving edge references.

    Scoped to the ids handed in — a node orphaned by an earlier import is not
    this save's business.
    """
    referenced: set[str] = set()
    for source, target in surviving_edges:
        referenced.add(source)
        referenced.add(target)
    return {node_id for node_id in candidate_ids if node_id not in referenced}


def validate_edge_endpoints(source_id: str, target_id: str) -> None:
    """Reject an edge that would start and end at the same node."""
    if source_id == target_id:
        raise DegenerateEdgeError(
            "An edge cannot start and end at the same node. Move one endpoint "
            "further from the other, or draw two edges."
        )
