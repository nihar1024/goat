"""Batch edits to a bundle's editable member layer.

One request, one transaction, because the edges layer and the nodes layer only
make sense together: the edge query in the artifact build inner-joins them, so an
edge naming a node that was never written is dropped and the street silently
disappears from routing.

The client draws edges. Everything about the nodes layer is decided here —
reuse a node within tolerance, split the edge the endpoint landed on, or mint a
node — so a user never has to keep source_node and target_node honest by hand.
"""

import asyncio
import logging
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from goatlib.bundles.importers.street_network.overture.flatten import (
    CLASS_DEFAULT_MAXSPEED,
    ROUTING_CLASSES,
)
from goatlib.bundles.topology import (
    DegenerateEdgeError,
    EdgeCandidate,
    MintNode,
    NodeCandidate,
    ReuseNode,
    SplitEdge,
    orphaned_nodes,
    resolve_endpoint,
    validate_edge_endpoints,
)
from goatlib.models.bundle import BundleTypeName, get_spec
from pydantic import BaseModel, Field
from shapely.geometry import Point, shape
from shapely.ops import transform as shapely_transform

from geoapi.dependencies import LayerInfo, LayerInfoDep, get_layer_info_sync
from geoapi.deps.auth import get_user_id
from geoapi.ducklake_write import ducklake_write_manager
from geoapi.routers.features_write import _invalidate_caches_and_pmtiles
from geoapi.services import bundle_edit_service as writer
from geoapi.services.layer_service import layer_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bundle Edits"])

UserIdDep = Annotated[UUID, Depends(get_user_id)]

# Metres. An endpoint this close to a node is taken to mean that node.
SNAP_TOLERANCE_M = 1.0

# What a drawn edge is when nobody said. The artifact build already maps any
# class it does not recognise to this, and it carries a drivable default speed,
# so an edit never fails for want of a classification.
DEFAULT_EDGE_CLASS = "unknown"

# How far beyond the edit's own extent to look for snap candidates. Overshooting
# costs a few extra rows; undershooting would hide a node the endpoint should
# have snapped to.
CANDIDATE_PAD_M = 50.0


class EdgeCreate(BaseModel):
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class EdgeUpdate(BaseModel):
    id: str
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class BundleEditBatch(BaseModel):
    base_revision: int
    create: list[EdgeCreate] = Field(default_factory=list)
    update: list[EdgeUpdate] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)


class EdgeSplit(BaseModel):
    original_id: str
    halves: list[str]


class EdgeChanges(BaseModel):
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
    split: list[EdgeSplit] = Field(default_factory=list)


class NodeChanges(BaseModel):
    created: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class BundleEditResponse(BaseModel):
    revision: int
    artifact_status: Literal["stale"]
    bundle_id: str
    # The client has to refresh this layer's tiles too — the server may have
    # minted or pruned nodes — and cannot know which layer it is otherwise.
    nodes_layer_id: str
    edges: EdgeChanges
    nodes: NodeChanges


async def authorize_edit(layer_info: LayerInfo, user_id: UUID) -> None:
    """The same write rule the per-feature endpoints apply.

    Deliberately not ``_get_authorized_metadata``: that refuses every write to a
    bundle member, which is exactly what this endpoint exists to allow. The
    access rule itself — owner, or a non-owner who shares an editable project
    with the owner — is unchanged.
    """
    metadata = await layer_service.get_layer_metadata(layer_info)
    if not metadata:
        raise HTTPException(status_code=404, detail="Collection not found")
    if not metadata.user_id:
        raise HTTPException(
            status_code=403, detail="You do not have permission to modify this layer"
        )
    if metadata.user_id == str(user_id).replace("-", ""):
        return
    if not await layer_service.user_can_edit_layer(layer_info.layer_id, user_id):
        raise HTTPException(
            status_code=403, detail="You do not have permission to modify this layer"
        )


def _pool() -> Any:
    """The Postgres pool, or a 503 if the app has not finished starting.

    Every helper below needs it, so the check lives in one place rather than
    being remembered four times.
    """
    pool = layer_service._pool
    if not pool:
        raise HTTPException(status_code=503, detail="Database pool not initialized")
    return pool


async def resolve_bundle_member(layer_id: str) -> dict[str, Any] | None:
    """The bundle, type and role of a layer, or None if it is not a member."""
    row = await _pool().fetchrow(
        """
        SELECT bl.bundle_id, bl.role, b.bundle_type, b.user_id
        FROM customer.bundle_layer bl
        JOIN customer.bundle b ON b.id = bl.bundle_id
        WHERE bl.layer_id = $1::uuid
        """,
        layer_id,
    )
    return dict(row) if row else None


async def read_bundle_revision(bundle_id: str) -> int:
    """The bundle's current layers_revision."""
    row = await _pool().fetchrow(
        "SELECT layers_revision FROM customer.bundle WHERE id = $1::uuid", bundle_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Bundle not found")
    return int(row["layers_revision"])


async def member_layer_of_role(bundle_id: str, role: str) -> dict[str, Any] | None:
    """A sibling member layer of the same bundle, by role."""
    row = await _pool().fetchrow(
        """
        SELECT bl.layer_id, l.user_id
        FROM customer.bundle_layer bl
        JOIN customer.layer l ON l.id = bl.layer_id
        WHERE bl.bundle_id = $1::uuid AND bl.role = $2
        """,
        bundle_id,
        role,
    )
    return dict(row) if row else None


async def mark_artifacts_stale(bundle_id: str) -> None:
    """Stop tools routing on a graph that no longer matches the layers.

    Done before the layer write, not after: if the write then fails, the
    artifact is stale over unchanged layers, which a rebuild fixes. The other
    order would leave a ready graph that disagrees with the data.
    """
    await _pool().execute(
        """
        UPDATE customer.bundle_artifact SET status = 'stale', updated_at = NOW()
        WHERE bundle_id = $1::uuid AND status <> 'stale'
        """,
        bundle_id,
    )


async def bump_bundle_revision(bundle_id: str) -> int:
    """Advance the revision so an in-flight rebuild knows it was overtaken."""
    row = await _pool().fetchrow(
        """
        UPDATE customer.bundle
        SET layers_revision = layers_revision + 1, updated_at = NOW()
        WHERE id = $1::uuid
        RETURNING layers_revision
        """,
        bundle_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Bundle not found")
    return int(row["layers_revision"])


def _to_3857(geometry: dict[str, Any]) -> Any:
    """Project a 4326 GeoJSON geometry into metres for measuring distances."""
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    return shapely_transform(transformer.transform, shape(geometry))


def _batch_bbox_3857(
    geometries: list[dict[str, Any]],
) -> tuple[float, float, float, float]:
    """Bounding box of everything being written, padded for the candidate scan."""
    bounds = [_to_3857(g).bounds for g in geometries]
    xmin = min(b[0] for b in bounds) - CANDIDATE_PAD_M
    ymin = min(b[1] for b in bounds) - CANDIDATE_PAD_M
    xmax = max(b[2] for b in bounds) + CANDIDATE_PAD_M
    ymax = max(b[3] for b in bounds) + CANDIDATE_PAD_M
    return (xmin, ymin, xmax, ymax)


def _fill_class_defaults(properties: dict[str, Any]) -> dict[str, Any]:
    """Give a drawn edge a class, and the speeds that class implies.

    An unclassified edge defaults to ``unknown`` rather than failing the save:
    classifying a street is a judgement the user can make later, and the routing
    engine already has a meaning for it.

    Speeds matter more than they look. The artifact build coalesces a null speed
    to 0 and the engine treats maxspeed <= 0 as impassable, so an edge saved
    without them would be walkable but invisible to car routing.
    """
    filled = dict(properties)
    if not filled.get("class"):
        filled["class"] = DEFAULT_EDGE_CLASS
    default = CLASS_DEFAULT_MAXSPEED.get(filled.get("class"))
    for column in ("speed_limit_kph_forward", "speed_limit_kph_backward"):
        if filled.get(column) is None and default is not None:
            filled[column] = default
    return filled


@router.post(
    "/collections/{collectionId}/edits",
    summary="Apply a batch of edits to a bundle's editable member layer",
    response_model=BundleEditResponse,
    status_code=200,
)
async def apply_bundle_edits(
    layer_info: LayerInfoDep,
    user_id: UserIdDep,
    body: BundleEditBatch = Body(...),
) -> BundleEditResponse:
    """Write an edge batch, derive the nodes it implies, and stale the graph."""
    await authorize_edit(layer_info, user_id)

    member = await resolve_bundle_member(layer_info.layer_id)
    if member is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "This layer is not part of a bundle. Use the ordinary feature "
                "endpoints instead."
            ),
        )

    bundle_id = str(member["bundle_id"])
    role = member["role"]
    spec_role = get_spec(BundleTypeName(member["bundle_type"])).role(role or "")
    if not (spec_role and spec_role.editable):
        raise HTTPException(
            status_code=400,
            detail=f"The '{role}' role of this bundle is not editable.",
        )

    if not (body.create or body.update or body.delete):
        raise HTTPException(status_code=400, detail="The batch contains no edits.")

    # An absent class is filled in below; one the engine does not know is not,
    # because the build would silently map it to a drivable road rather than
    # report the mistake.
    stated_classes = [e.properties.get("class") for e in body.create] + [
        e.properties.get("class") for e in body.update
    ]
    for stated in stated_classes:
        if stated and stated not in ROUTING_CLASSES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{stated}' is not a street class the router knows. "
                    f"Accepted: {', '.join(sorted(ROUTING_CLASSES))}."
                ),
            )

    current_revision = await read_bundle_revision(bundle_id)
    if current_revision != body.base_revision:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This network changed while you were editing (revision "
                f"{current_revision}, you started from {body.base_revision}). "
                "Reload before saving."
            ),
        )

    nodes_member = await member_layer_of_role(bundle_id, "nodes")
    if nodes_member is None:
        raise HTTPException(
            status_code=400,
            detail="This bundle has no nodes layer, so edges cannot be edited.",
        )
    if str(nodes_member["user_id"]) != str(member["user_id"]):
        raise HTTPException(
            status_code=403,
            detail="This bundle's member layers have different owners.",
        )

    loop = asyncio.get_event_loop()
    nodes_info: LayerInfo = await loop.run_in_executor(
        None, get_layer_info_sync, str(nodes_member["layer_id"])
    )

    await mark_artifacts_stale(bundle_id)

    try:
        changes = await loop.run_in_executor(
            None, _apply, layer_info, nodes_info, body
        )
    except DegenerateEdgeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    revision = await bump_bundle_revision(bundle_id)

    # Once per layer, not once per feature: PMTiles are deleted so tiles fall
    # back to dynamic generation, and doing that per edge would rebuild them
    # for every stroke of an edit.
    await _invalidate_caches_and_pmtiles(layer_info)
    await _invalidate_caches_and_pmtiles(nodes_info)

    return BundleEditResponse(
        revision=revision,
        artifact_status="stale",
        bundle_id=bundle_id,
        nodes_layer_id=str(nodes_member["layer_id"]),
        edges=changes[0],
        nodes=changes[1],
    )


def _apply(
    edges_info: LayerInfo, nodes_info: LayerInfo, body: BundleEditBatch
) -> tuple[EdgeChanges, NodeChanges]:
    """Derive and write, in one transaction."""
    edges_table = edges_info.full_table_name
    nodes_table = nodes_info.full_table_name
    edge_changes = EdgeChanges()
    node_changes = NodeChanges()

    written = [e.geometry for e in body.create] + [e.geometry for e in body.update]

    with ducklake_write_manager.connection() as con:
        columns = writer.column_names(con, edges_table)
        node_columns = writer.column_names(con, nodes_table)
        con.execute("BEGIN")
        try:
            touched = list(body.delete) + [e.id for e in body.update]
            resolved = writer.resolve_feature_ids(con, edges_table, touched)

            def own_id(feature_id: str) -> str:
                """The layer's own id for a feature the editor referred to."""
                if not str(feature_id).isdigit():
                    # Already a layer id: an edge this session created.
                    return feature_id
                own = resolved.get(str(feature_id))
                if own is None:
                    # Falling back to the raw value would target whatever row
                    # happened to carry it as an id — usually none, which used to
                    # make the whole edit a silent no-op.
                    raise ValueError(
                        "Part of this edit refers to a feature that is no longer "
                        "in the layer. Reload before saving."
                    )
                return own

            delete_ids = [own_id(fid) for fid in body.delete]
            update_ids = {e.id: own_id(e.id) for e in body.update}

            candidate_nodes: list[NodeCandidate] = []
            candidate_edges: list[EdgeCandidate] = []
            if written:
                candidate_nodes, candidate_edges = writer.fetch_candidates(
                    con,
                    edges_table,
                    nodes_table,
                    _batch_bbox_3857(written),
                    exclude_edge_ids=set(delete_ids) | set(update_ids.values()),
                )

            # Nodes the save might orphan: the endpoints of everything it
            # removes or moves.
            release_candidates = _endpoints_of(
                con, edges_table, delete_ids + list(update_ids.values())
            )

            for created in body.create:
                new_id = writer.mint_id()
                source, target = _resolve_ends(
                    con,
                    edges_table,
                    nodes_table,
                    columns,
                    node_columns,
                    created.geometry,
                    candidate_nodes,
                    candidate_edges,
                    edge_changes,
                    node_changes,
                )
                validate_edge_endpoints(source, target)
                writer.insert_edge(
                    con,
                    edges_table,
                    columns,
                    new_id,
                    created.geometry,
                    _fill_class_defaults(created.properties),
                    source,
                    target,
                )
                edge_changes.created.append(new_id)

            for updated in body.update:
                source, target = _resolve_ends(
                    con,
                    edges_table,
                    nodes_table,
                    columns,
                    node_columns,
                    updated.geometry,
                    candidate_nodes,
                    candidate_edges,
                    edge_changes,
                    node_changes,
                )
                validate_edge_endpoints(source, target)
                writer.update_edge(
                    con,
                    edges_table,
                    columns,
                    update_ids[updated.id],
                    updated.geometry,
                    # An update replaces the row's properties, so it needs the
                    # same defaults a create gets — otherwise saving an edge
                    # without restating its class would null it out.
                    _fill_class_defaults(updated.properties),
                    source,
                    target,
                )
                edge_changes.updated.append(update_ids[updated.id])

            if delete_ids:
                writer.delete_edges_by_id(con, edges_table, delete_ids)
                edge_changes.deleted.extend(delete_ids)

            if release_candidates:
                surviving = writer.surviving_edge_endpoints(
                    con, edges_table, list(release_candidates)
                )
                orphans = orphaned_nodes(release_candidates, surviving)
                writer.delete_nodes_by_id(con, nodes_table, orphans)
                node_changes.removed.extend(sorted(orphans))

            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise

    return edge_changes, node_changes


def _endpoints_of(con: Any, edges_table: str, edge_ids: list[str]) -> set[str]:
    """Node ids the given edges currently reference."""
    if not edge_ids:
        return set()
    placeholders = ", ".join(["?"] * len(edge_ids))
    rows = con.execute(
        f'SELECT source_node, target_node FROM {edges_table} '
        f'WHERE "id" IN ({placeholders})',
        list(edge_ids),
    ).fetchall()
    return {value for row in rows for value in row if value}


def _resolve_ends(
    con: Any,
    edges_table: str,
    nodes_table: str,
    edge_columns: list[str],
    node_columns: list[str],
    geometry: dict[str, Any],
    candidate_nodes: list[NodeCandidate],
    candidate_edges: list[EdgeCandidate],
    edge_changes: EdgeChanges,
    node_changes: NodeChanges,
) -> tuple[str, str]:
    """Node ids for an edge's two endpoints, creating or splitting as needed."""
    projected = _to_3857(geometry)
    coords = list(projected.coords)
    if len(coords) < 2:
        raise ValueError("An edge needs at least two points.")

    resolved: list[str] = []
    for x, y in (coords[0], coords[-1]):
        decision = resolve_endpoint(
            Point(x, y), candidate_nodes, candidate_edges, SNAP_TOLERANCE_M
        )
        if isinstance(decision, ReuseNode):
            resolved.append(decision.node_id)
            continue

        node_id = writer.mint_id()
        if isinstance(decision, SplitEdge):
            writer.insert_node_on_edge(
                con,
                nodes_table,
                node_columns,
                edges_table,
                node_id,
                decision.edge_id,
                decision.fraction,
            )
            left, right = writer.mint_id(), writer.mint_id()
            writer.split_edge(
                con,
                edges_table,
                edge_columns,
                decision.edge_id,
                decision.fraction,
                left,
                right,
                node_id,
            )
            edge_changes.split.append(
                EdgeSplit(original_id=decision.edge_id, halves=[left, right])
            )
            # The halves replace the candidate, so a later endpoint in the same
            # batch cannot split an edge that no longer exists.
            candidate_edges[:] = [
                e for e in candidate_edges if e.edge_id != decision.edge_id
            ]
        else:
            assert isinstance(decision, MintNode)
            writer.insert_node(
                con, nodes_table, node_columns, node_id, decision.x, decision.y
            )

        node_changes.created.append(node_id)
        candidate_nodes.append(
            NodeCandidate(node_id=node_id, x=float(x), y=float(y))
        )
        resolved.append(node_id)

    return resolved[0], resolved[1]
