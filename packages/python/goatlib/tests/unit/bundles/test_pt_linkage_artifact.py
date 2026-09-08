"""The PT stop-to-street linkage artifact.

The build itself needs the routing extension and a real network, so what is
pinned here is everything around it: which inputs are refused and how, that a
refusal costs only the linkage, and that the archive a build writes is the one
a consumer can read a single mode out of.
"""

import tarfile
from pathlib import Path

import pytest
from goatlib.bundles.artifacts.base import BuiltArtifact
from goatlib.bundles.artifacts.build_mixin import BundleArtifactBuildMixin
from goatlib.bundles.artifacts.gtfs import (
    DEFAULT_LINKAGE_MODES,
    LINKAGE_MODES,
    GtfsArtifactBuilder,
    linkage_member,
    unpack_pt_linkage,
)
from goatlib.models.bundle import BundleArtifactKind, BundleTypeName, get_spec

STREET = {"edge_path": "/edges.parquet", "node_path": "/nodes.parquet"}


@pytest.fixture
def builder() -> GtfsArtifactBuilder:
    return GtfsArtifactBuilder()


def test_builder_produces_both_declared_artifacts(builder) -> None:
    """The spec declares two; a kind the spec declares and nothing builds shows
    as an artifact that never appears, which reads as "still importing"."""
    spec = get_spec(builder.bundle_type)
    assert set(builder.produces) == set(spec.artifacts)


def test_walking_is_the_default_and_modes_deduplicate(builder) -> None:
    assert DEFAULT_LINKAGE_MODES == ("walking",)
    assert builder._requested_modes(None) == ("walking",)
    assert builder._requested_modes({}) == ("walking",)
    assert builder._requested_modes({"linkage_modes": ["car", "car", "walking"]}) == (
        "car",
        "walking",
    )


def test_an_unusable_street_network_fails_only_the_linkage(builder, tmp_path) -> None:
    """No street network in the dependencies means a linked one is broken —
    the caller substitutes the default network when nothing is linked. Either
    way the timetable built in the same pass is unaffected."""
    result = builder._build_linkage(
        timetable_path="/tt.bin",
        workdir=str(tmp_path),
        dependencies={},
        modes=("walking",),
    )
    assert result.kind is BundleArtifactKind.pt_network_linkage
    assert result.local_path is None
    assert "not ready to route on" in result.error


@pytest.mark.asyncio
async def test_an_unlinked_bundle_falls_back_to_the_default_network(
    tmp_path,
) -> None:
    """A PT bundle is usable without a street network of its own: the stops
    still have to reach somewhere, so the linkage is computed against the
    default global network."""

    class _Db:
        async def get_bundle_dependency(self, bundle_id: str, kind: str) -> None:
            return None

    class _Settings:
        street_network_edges_base_path = "/global/edges"
        street_network_nodes_base_path = "/global/nodes"

    class _Runner(BundleArtifactBuildMixin):
        settings = _Settings()

    resolved = await _Runner()._resolve_dependencies(
        _Db(),
        bundle_id="b",
        spec=get_spec(BundleTypeName.pt_network_gtfs),
        workdir=str(tmp_path),
    )
    assert resolved["street_network"] == {
        "bundle_id": None,
        "edge_path": "/global/edges",
        "node_path": "/global/nodes",
    }


def test_unknown_mode_names_the_ones_that_exist(builder, tmp_path) -> None:
    result = builder._build_linkage(
        timetable_path="/tt.bin",
        workdir=str(tmp_path),
        dependencies={"street_network": STREET},
        modes=("hovercraft",),
    )
    assert "hovercraft" in result.error
    for mode in LINKAGE_MODES:
        assert mode in result.error


def test_a_built_artifact_is_a_file_or_a_reason_never_both() -> None:
    kind = BundleArtifactKind.pt_network_linkage
    with pytest.raises(ValueError):
        BuiltArtifact(kind=kind)
    with pytest.raises(ValueError):
        BuiltArtifact(kind=kind, local_path="/x.tar", error="also failed")


def _archive(root: Path, *modes: str) -> Path:
    src = root / "src"
    src.mkdir()
    archive = root / "pt_network_linkage.tar"
    with tarfile.open(archive, "w") as tar:
        for mode in modes:
            member = src / linkage_member(mode)
            member.write_bytes(b"parquet")
            tar.add(member, arcname=member.name)
    return archive


def test_one_mode_is_read_back_out_of_the_archive(tmp_path) -> None:
    archive = _archive(tmp_path, "walking", "car")
    table = unpack_pt_linkage(archive, tmp_path / "dest", "walking")
    assert Path(table).name == linkage_member("walking")
    assert Path(table).exists()


def test_a_mode_the_bundle_lacks_says_what_it_has(tmp_path) -> None:
    archive = _archive(tmp_path, "walking")
    with pytest.raises(ValueError) as excinfo:
        unpack_pt_linkage(archive, tmp_path / "dest", "car")
    message = str(excinfo.value)
    assert "car" in message
    assert "walking" in message
