"""The bundle batch-edit endpoint.

Two concerns: what the endpoint refuses before touching anything, and the
id/attribute handling that decides whether a save actually lands.
"""

from unittest.mock import AsyncMock, patch

import duckdb
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

LAYER = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
BUNDLE = "22222222-2222-2222-2222-222222222222"
EDITS_URL = f"/collections/{LAYER}/edits"


@pytest.fixture
def client(mock_ducklake_manager):
    from geoapi.dependencies import LayerInfo, get_layer_info
    from geoapi.main import app

    # Resolving a LayerInfo would hit the DuckLake catalog for the layer's
    # schema. The endpoint's own logic is what these tests are about.
    app.dependency_overrides[get_layer_info] = lambda: LayerInfo(
        layer_id=LAYER, schema_name="user_data", table_name="layer_test"
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _allow_edit():
    with patch(
        "geoapi.routers.bundle_edits.authorize_edit", AsyncMock(return_value=None)
    ):
        yield


def _member(role="edges", user_id="owner-a"):
    return {
        "bundle_id": BUNDLE,
        "bundle_type": "street_network",
        "role": role,
        "user_id": user_id,
    }


def _payload(base_revision=0, properties=None, **overrides):
    payload = {
        "base_revision": base_revision,
        "create": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[11.0, 48.0], [11.001, 48.0]],
                },
                "properties": (
                    {"class": "residential"} if properties is None else properties
                ),
            }
        ],
        "update": [],
        "delete": [],
    }
    payload.update(overrides)
    return payload


def _post(
    client, payload, member=None, revision=0, nodes_owner="owner-a", apply_raises=None
):
    """Post a batch with the surrounding lookups stubbed."""
    with (
        patch(
            "geoapi.routers.bundle_edits.resolve_bundle_member",
            AsyncMock(return_value=_member() if member is None else member),
        ),
        patch(
            "geoapi.routers.bundle_edits.read_bundle_revision",
            AsyncMock(return_value=revision),
        ),
        patch(
            "geoapi.routers.bundle_edits.member_layer_of_role",
            AsyncMock(return_value={"layer_id": LAYER, "user_id": nodes_owner}),
        ),
        patch(
            "geoapi.routers.bundle_edits.mark_artifacts_stale",
            AsyncMock(return_value=None),
        ),
        patch("geoapi.routers.bundle_edits.get_layer_info_sync"),
        patch(
            "geoapi.routers.bundle_edits.bump_bundle_revision",
            AsyncMock(return_value=revision + 1),
        ),
        patch(
            "geoapi.routers.bundle_edits._invalidate_caches_and_pmtiles",
            AsyncMock(return_value=None),
        ),
        patch("geoapi.routers.bundle_edits._apply") as apply_mock,
    ):
        from geoapi.routers.bundle_edits import EdgeChanges, NodeChanges

        if apply_raises is not None:
            apply_mock.side_effect = apply_raises
        else:
            apply_mock.return_value = (EdgeChanges(), NodeChanges())
        return client.post(EDITS_URL, json=payload)


# --- what the endpoint refuses ---------------------------------------------


@pytest.mark.parametrize(
    ("case", "member", "revision", "status", "fragment"),
    [
        ("role is not editable", _member("nodes"), 0, 400, "editable"),
        # The client started from 0 while the network has moved on to 9.
        ("stale base revision", _member(), 9, 409, "9"),
    ],
)
def test_refusals(client, case, member, revision, status, fragment):
    response = _post(client, _payload(), member=member, revision=revision)
    assert response.status_code == status
    assert fragment in str(response.json()["detail"])


def test_a_layer_outside_any_bundle_is_refused(client):
    with patch(
        "geoapi.routers.bundle_edits.resolve_bundle_member",
        AsyncMock(return_value=None),
    ):
        response = client.post(EDITS_URL, json=_payload())
    assert response.status_code == 400
    assert "bundle" in response.json()["detail"].lower()


def test_an_empty_batch_and_an_unknown_class_are_both_refused(client):
    empty = _post(client, {"base_revision": 0, "create": [], "update": [], "delete": []})
    assert empty.status_code == 400
    assert "no edits" in empty.json()["detail"].lower()

    # A typo would otherwise be mapped to a drivable road by the build.
    bogus = _post(client, _payload(properties={"class": "banna"}))
    assert bogus.status_code == 400
    assert "banna" in bogus.json()["detail"]


def test_mismatched_member_owners_are_refused(client):
    """A bundle whose members have different owners is not safe to write."""
    response = _post(client, _payload(), nodes_owner="owner-b")
    assert response.status_code == 403
    assert "owner" in response.json()["detail"].lower()


def test_authorization_runs_before_anything_else(client):
    """A refused edit never reaches the bundle lookup."""
    member_lookup = AsyncMock(return_value=_member())
    with (
        patch(
            "geoapi.routers.bundle_edits.authorize_edit",
            AsyncMock(side_effect=HTTPException(status_code=403, detail="nope")),
        ),
        patch("geoapi.routers.bundle_edits.resolve_bundle_member", member_lookup),
    ):
        response = client.post(EDITS_URL, json=_payload())
    assert response.status_code == 403
    member_lookup.assert_not_called()


def test_a_degenerate_edge_is_a_bad_request_not_a_server_error(client):
    from goatlib.bundles.topology import DegenerateEdgeError

    response = _post(
        client, _payload(), apply_raises=DegenerateEdgeError("same node")
    )
    assert response.status_code == 400
    assert "same node" in response.json()["detail"]


def test_an_edge_with_no_class_is_accepted(client):
    """Classifying a street is a judgement the user can make later."""
    assert _post(client, _payload(properties={})).status_code == 200


# --- attribute defaults ----------------------------------------------------


def test_class_and_speed_defaults():
    """An unclassified edge must still be routable, and a footway must not be
    drivable: the build coalesces a null speed to 0, which the engine reads as
    impassable."""
    from goatlib.bundles.importers.street_network.overture.flatten import (
        CLASS_DEFAULT_MAXSPEED,
        ROUTING_CLASSES,
    )

    from geoapi.routers.bundle_edits import DEFAULT_EDGE_CLASS, _fill_class_defaults

    assert DEFAULT_EDGE_CLASS in ROUTING_CLASSES
    filled = _fill_class_defaults({})
    assert filled["class"] == DEFAULT_EDGE_CLASS
    assert (
        filled["speed_limit_kph_forward"] == CLASS_DEFAULT_MAXSPEED[DEFAULT_EDGE_CLASS]
    )

    stated = _fill_class_defaults({"class": "footway"})
    assert stated["class"] == "footway"
    assert "speed_limit_kph_forward" not in stated


# --- feature ids and no-op writes ------------------------------------------


@pytest.fixture
def edges_table():
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial")
    con.execute(
        "CREATE TABLE edges (id VARCHAR, geometry GEOMETRY, "
        "source_node VARCHAR, target_node VARCHAR)"
    )
    con.execute(
        "INSERT INTO edges VALUES ('edge-a', NULL, NULL, NULL), "
        "('edge-b', NULL, NULL, NULL), ('edge-c', NULL, NULL, NULL)"
    )
    yield con
    con.close()


def test_feature_ids_resolve_through_the_rowid_plus_one_convention(edges_table):
    """A tile feature id is rowid + 1; treating it as a rowid targets the wrong row.

    Getting this wrong made an edit to an existing edge a silent no-op: the
    UPDATE matched nothing and the client still reported success, so the edge
    appeared to revert on the next tile refresh.
    """
    from geoapi.services.bundle_edit_service import resolve_feature_ids

    assert resolve_feature_ids(edges_table, "edges", ["1", "3"]) == {
        "1": "edge-a",
        "3": "edge-c",
    }
    # Past the end of the table, and an id this session minted: neither resolves,
    # and the caller must treat that as an error rather than guess.
    assert resolve_feature_ids(edges_table, "edges", ["99", "edit:abc"]) == {}


def test_writes_that_match_nothing_raise(edges_table):
    """A save that changes nothing must not look like a successful one."""
    from geoapi.services.bundle_edit_service import delete_edges_by_id, update_edge

    with pytest.raises(ValueError, match="no longer in the layer"):
        update_edge(
            edges_table,
            "edges",
            ["id", "geometry", "source_node", "target_node"],
            "ghost-edge",
            {"type": "LineString", "coordinates": [[11.0, 48.0], [11.001, 48.0]]},
            {},
            "n1",
            "n2",
        )

    with pytest.raises(ValueError, match="no longer in the layer"):
        delete_edges_by_id(edges_table, "edges", ["edge-a", "ghost"])
    # The batch is refused whole: the edge that does exist is untouched.
    assert edges_table.execute("SELECT count(*) FROM edges").fetchone()[0] == 3
