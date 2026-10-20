from fastapi import FastAPI
from starlette.responses import Response
from starlette.testclient import TestClient

from geoapi.middleware import credit_metering as cm
from geoapi.services.layer_service import LayerMetadata

LYR = "0b8f3a4e-5c1d-4e6a-9f27-3d1c2b4a5e60"


def test_layer_metadata_carries_org_and_owner_through_serialization():
    m = LayerMetadata(
        layer_id="L",
        name="n",
        geometry_type="point",
        bounds=[0, 0, 1, 1],
        columns=[],
        user_id="owner-1",
        organization_id="org-1",
    )
    assert m.organization_id == "org-1"
    assert m.user_id == "owner-1"
    again = LayerMetadata.from_dict(m.to_dict())
    assert again.organization_id == "org-1"  # survives the Redis cache roundtrip
    assert again.user_id == "owner-1"


def test_collection_and_service_classification():
    assert cm._collection_id_from_path("/collections/abc/tiles/x/1/2/3") == "abc"
    assert cm._collection_id_from_path("/healthz") is None
    assert cm._service_from_path("/collections/abc/tiles/x/1/2/3") == "tiles"
    assert cm._service_from_path("/collections/abc/items") == "features"
    assert cm._service_from_path("/collections/abc/items/5") == "features"
    assert cm._service_from_path("/collections/abc/download") == "downloads"


def _app(monkeypatch, *, org, owner, over_budget, recorder):
    async def _resolve(cid):
        return (org, owner)

    async def _over(o):
        return over_budget

    async def _record(*args):
        recorder.append(args)

    monkeypatch.setattr(cm, "_resolve_layer_org", _resolve)
    monkeypatch.setattr(cm, "_is_over_budget", _over)
    monkeypatch.setattr(cm, "_record", _record)

    app = FastAPI()
    app.add_middleware(cm.CreditMeteringMiddleware)

    @app.get("/collections/{cid}/items")
    def items(cid: str):
        return Response(content=b"x" * 200, media_type="application/json")

    @app.get("/collections/{cid}/download")
    def download(cid: str):
        return Response(content=b"x" * 300, media_type="application/octet-stream")

    return app


def test_records_full_dimension_when_under_budget(monkeypatch):
    rec = []
    client = TestClient(
        _app(monkeypatch, org="org1", owner="own1", over_budget=False, recorder=rec)
    )
    # anonymous (no Authorization header)
    client.get(f"/collections/{LYR}/items")
    # _record(org, owner, layer, service, size, anonymous)
    assert rec == [("org1", "own1", LYR, "features", 200, True)]


def test_authenticated_request_not_anonymous(monkeypatch):
    rec = []
    client = TestClient(
        _app(monkeypatch, org="org1", owner="own1", over_budget=False, recorder=rec)
    )
    client.get(f"/collections/{LYR}/items", headers={"Authorization": "Bearer t"})
    org, owner, layer, service, size, anonymous = rec[0]
    assert anonymous is False


def test_blocks_downloads_when_over_budget(monkeypatch):
    rec = []
    client = TestClient(
        _app(monkeypatch, org="org1", owner="own1", over_budget=True, recorder=rec)
    )
    resp = client.get(f"/collections/{LYR}/download")
    assert resp.status_code == 402
    assert rec == []  # blocked before serving


def test_maps_keep_working_when_over_budget(monkeypatch):
    # A published map or dashboard must not go dark: features and tiles are
    # served (and still metered) when the organization is out of credits.
    rec = []
    client = TestClient(
        _app(monkeypatch, org="org1", owner="own1", over_budget=True, recorder=rec)
    )
    resp = client.get(f"/collections/{LYR}/items")
    assert resp.status_code == 200
    assert rec == [("org1", "own1", LYR, "features", 200, True)]


def _layer_app(monkeypatch, recorder, *, resolves=True):
    async def _resolve(cid):
        recorder.append(("resolve", cid))
        return ("org1", "own1") if resolves else (None, None)

    async def _record(*args):
        recorder.append(args)

    async def _over(o):
        return False

    monkeypatch.setattr(cm, "_resolve_layer_org", _resolve)
    monkeypatch.setattr(cm, "_is_over_budget", _over)
    monkeypatch.setattr(cm, "_record", _record)

    app = FastAPI()
    app.add_middleware(cm.CreditMeteringMiddleware)

    @app.api_route("/collections/{cid}/items", methods=["GET", "HEAD"])
    def items(cid: str):
        return Response(content=b"x" * 200, headers={"content-length": "200"})

    @app.get("/collections/{cid}/status/{code}")
    def status(cid: str, code: int):
        return Response(
            content=b"x" * 50, status_code=code, headers={"content-length": "50"}
        )

    return app


def _recorded(rec):
    return [r for r in rec if r[0] != "resolve"]


def test_layer_id_variants_share_one_counter_key(monkeypatch):
    rec = []
    client = TestClient(_layer_app(monkeypatch, rec))
    for variant in (LYR, LYR.upper(), LYR.replace("-", ""), f"urn:uuid:{LYR}"):
        client.get(f"/collections/{variant}/items")
    assert {r[2] for r in _recorded(rec)} == {LYR}
    assert len(_recorded(rec)) == 4
    assert {r[1] for r in rec if r[0] == "resolve"} == {LYR}  # lookups use it too


def test_paths_that_are_not_a_layer_are_neither_resolved_nor_counted(monkeypatch):
    rec = []
    client = TestClient(_layer_app(monkeypatch, rec))
    client.get("/collections/not-a-layer/items")
    assert rec == []


def test_unknown_layers_are_not_counted(monkeypatch):
    rec = []
    client = TestClient(_layer_app(monkeypatch, rec, resolves=False))
    client.get(f"/collections/{LYR}/items")
    assert _recorded(rec) == []


def test_only_get_with_200_or_206_is_metered(monkeypatch):
    rec = []
    client = TestClient(_layer_app(monkeypatch, rec))
    client.head(f"/collections/{LYR}/items")
    assert _recorded(rec) == []
    for code in (301, 304, 404, 500):
        client.get(f"/collections/{LYR}/status/{code}", follow_redirects=False)
    assert _recorded(rec) == []
    for code in (200, 206):
        client.get(f"/collections/{LYR}/status/{code}")
    assert [r[3:5] for r in _recorded(rec)] == [("features", 50), ("features", 50)]


def test_counter_hash_gets_a_ttl_on_every_write():
    calls = []

    class Pipe:
        def __getattr__(self, name):
            return lambda *a: calls.append((name, a))

        def execute(self):
            return []

    class Client:
        def pipeline(self):
            return Pipe()

    cm._record_sync(Client(), "org1", "own1", LYR, "tiles", 10, True)
    key = f"meter:egress:org1:{LYR}:tiles"
    assert ("expire", (key, 7 * 24 * 3600)) in calls
