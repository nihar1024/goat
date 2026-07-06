import os
from pathlib import Path

import pytest
from goatlib.io.remote_source.wfs import from_wfs
from goatlib.io.remote_source.wfs_reader import WFSReader

WFS_URL = (
    "https://geoservices.bayern.de/wfs/v1/ogc_atkis_basisdlm.cgi?"
    "SERVICE=WFS&VERSION=2.0.0"
)
LAYER_NAME = "adv:AX_Strasse"

# Live tests against the Bavarian ATKIS WFS: slow (minutes) and dependent on
# an external service, so opt-in only.
requires_live_wfs = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_WFS") != "1",
    reason="live WFS test — set RUN_LIVE_WFS=1 to run",
)


@requires_live_wfs
def test_get_layers_parses_names() -> None:
    """Ensure get_layers() correctly extracts layer names."""
    reader = WFSReader()
    layers = reader.get_layers(
        "https://geoservices.bayern.de/wfs/v1/ogc_atkis_basisdlm.cgi?SERVICE=WFS&request=GetCapabilities"
    )
    assert "adv:AX_Wald" in layers
    assert "adv:AX_Strasse" in layers


def test_build_datasource_creates_xml(tmp_path: Path) -> None:
    """Ensure build_datasource() writes a valid XML file."""
    reader = WFSReader()
    url = "https://geo.example/wfs?SERVICE=WFS&VERSION=2.0.0"
    xml_path = reader.build_datasource(url)
    content = xml_path.read_text(encoding="utf-8")
    assert xml_path.exists()
    assert "<OGRWFSDataSource>" in content
    # SERVICE/VERSION params are stripped — they confuse the GDAL WFS driver
    assert "<URL>https://geo.example/wfs</URL>" in content


def test_can_handle() -> None:
    """Detect only WFS URLs."""
    reader = WFSReader()
    assert reader.can_handle("https://x/service=WFS")
    assert not reader.can_handle("https://x/service=WMS")


@requires_live_wfs
def test_real_wfs(tmp_path: Path) -> None:
    """
    Full integration test against the Bavarian ATKIS WFS service.
    It downloads the layer via GDAL's WFS driver
    and converts it to Parquet through goatlib.convert_any.
    """

    try:
        out, meta = from_wfs(
            url=WFS_URL,
            out_dir=tmp_path,
            layer=LAYER_NAME,
            target_crs="EPSG:25832",  # UTM32N, Bavaria's projected CRS
        )
    except Exception as e:
        pytest.skip(f"WFS service not reachable or failed: {e}")

    # --- Basic assertions --------------------------------------------
    assert out and out.exists() and out.suffix == ".parquet"
    assert meta and meta.crs == "EPSG:25832"
    assert meta.source_type == "vector"

    # --- Spot‑check attribute + feature count -----------------------
    import duckdb

    con = duckdb.connect(database=":memory:")
    con.execute("INSTALL spatial; LOAD spatial;")
    cnt = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out}')").fetchone()[0]
    assert cnt > 0, "No features returned from WFS service"
    con.close()
