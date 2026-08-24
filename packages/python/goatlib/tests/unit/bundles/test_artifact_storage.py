"""Tests for artifact placement on the data volume.

Artifacts live next to DuckLake and tiles rather than in object storage, so the
guarantees a bucket used to provide — atomic replace, a stable key — have to hold
on the filesystem instead.
"""

from pathlib import Path

import pytest
from goatlib.bundles.artifacts.storage import (
    artifact_relative_path,
    delete_bundle_artifacts,
    resolve_artifact,
    store_artifact,
)

BUNDLE = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


@pytest.fixture
def built(tmp_path: Path) -> str:
    source = tmp_path / "build" / "graph.bin"
    source.parent.mkdir()
    source.write_bytes(b"graph-v1")
    return str(source)


def test_path_is_relative_and_keyed_by_bundle() -> None:
    """Relative so the mount point can move; bundle-keyed because a shared
    bundle may be rebuilt by someone other than its importer."""
    relative = artifact_relative_path(BUNDLE, "pt_network_graph", ".bin")

    assert relative == f"{BUNDLE}/pt_network_graph.bin"
    assert not Path(relative).is_absolute()


def test_store_writes_under_the_data_dir(tmp_path: Path, built: str) -> None:
    data_dir = tmp_path / "bundles"

    relative = store_artifact(
        built,
        bundles_data_dir=str(data_dir),
        bundle_id=BUNDLE,
        kind="pt_network_graph",
        suffix=".bin",
    )

    stored = data_dir / relative
    assert stored.read_bytes() == b"graph-v1"
    assert stored.parent.name == BUNDLE


def test_store_creates_missing_directories(tmp_path: Path, built: str) -> None:
    """First artifact on a fresh volume must not fail on a missing tree."""
    data_dir = tmp_path / "does" / "not" / "exist"

    relative = store_artifact(
        built,
        bundles_data_dir=str(data_dir),
        bundle_id=BUNDLE,
        kind="street_network_graph",
        suffix=".tar",
    )

    assert (data_dir / relative).is_file()


def test_rebuild_replaces_in_place(tmp_path: Path, built: str) -> None:
    data_dir = tmp_path / "bundles"
    first = store_artifact(
        built,
        bundles_data_dir=str(data_dir),
        bundle_id=BUNDLE,
        kind="pt_network_graph",
        suffix=".bin",
    )

    rebuilt = tmp_path / "build" / "graph2.bin"
    rebuilt.write_bytes(b"graph-v2")
    second = store_artifact(
        str(rebuilt),
        bundles_data_dir=str(data_dir),
        bundle_id=BUNDLE,
        kind="pt_network_graph",
        suffix=".bin",
    )

    assert first == second, "the path is stable, so stored rows stay valid"
    assert (data_dir / second).read_bytes() == b"graph-v2"
    assert [p.name for p in (data_dir / BUNDLE).iterdir()] == [
        "pt_network_graph.bin"
    ], "no staging file left behind"


def test_a_failed_store_leaves_no_partial_file(tmp_path: Path) -> None:
    """A reader must never see a half-written artifact."""
    data_dir = tmp_path / "bundles"

    with pytest.raises(OSError):
        store_artifact(
            str(tmp_path / "missing.bin"),
            bundles_data_dir=str(data_dir),
            bundle_id=BUNDLE,
            kind="pt_network_graph",
            suffix=".bin",
        )

    assert list((data_dir / BUNDLE).iterdir()) == []


def test_resolve_returns_the_absolute_path(tmp_path: Path, built: str) -> None:
    data_dir = tmp_path / "bundles"
    relative = store_artifact(
        built,
        bundles_data_dir=str(data_dir),
        bundle_id=BUNDLE,
        kind="pt_network_graph",
        suffix=".bin",
    )

    resolved = resolve_artifact(str(data_dir), relative)

    assert resolved == data_dir / relative
    assert resolved is not None and resolved.is_absolute()


def test_resolve_reports_a_row_whose_file_is_gone(tmp_path: Path) -> None:
    """A restored volume can predate a build; artifacts are regenerable, so the
    caller is told 'absent' rather than handed a path that fails to open."""
    assert resolve_artifact(str(tmp_path), f"{BUNDLE}/pt_network_graph.bin") is None


def test_delete_removes_every_artifact_of_the_bundle(
    tmp_path: Path, built: str
) -> None:
    data_dir = tmp_path / "bundles"
    for kind, suffix in (("pt_network_graph", ".bin"), ("pt_network_linkage", ".bin")):
        store_artifact(
            built,
            bundles_data_dir=str(data_dir),
            bundle_id=BUNDLE,
            kind=kind,
            suffix=suffix,
        )
    other = "0000ffff-5717-4562-b3fc-2c963f66afa6"
    store_artifact(
        built,
        bundles_data_dir=str(data_dir),
        bundle_id=other,
        kind="pt_network_graph",
        suffix=".bin",
    )

    removed = delete_bundle_artifacts(str(data_dir), BUNDLE)

    assert removed == 2
    assert not (data_dir / BUNDLE).exists()
    assert (data_dir / other).is_dir(), "another bundle's artifacts are untouched"


def test_delete_is_a_noop_when_nothing_was_built(tmp_path: Path) -> None:
    assert delete_bundle_artifacts(str(tmp_path), BUNDLE) == 0
