"""Editing a bundle: which roles allow it, and how a rebuild publishes.

Covers the spec-level contract (``RoleSpec.editable``), the bookkeeping a
rebuild depends on (upsert, revision-guarded publish), and the wiring that makes
the rebuild tool reachable.
"""

import pytest
from pydantic import ValidationError

from goatlib.bundles.artifacts.build_mixin import BundleArtifactBuildMixin
from goatlib.bundles.runner import BundleImportRunner
from goatlib.models.bundle import SPECS, BundleTypeName, RoleSpec
from goatlib.tools.bundle_artifact_rebuild import (
    BundleArtifactRebuildParams,
    BundleArtifactRebuildRunner,
)
from goatlib.tools.db import ToolDatabaseService
from goatlib.tools.registry import TOOL_REGISTRY

USER = "11111111-1111-1111-1111-111111111111"
BUNDLE = "22222222-2222-2222-2222-222222222222"
ARTIFACT = "33333333-3333-3333-3333-333333333333"


# --- editability -----------------------------------------------------------


@pytest.mark.parametrize(
    ("bundle_type", "role", "expected"),
    [
        (BundleTypeName.street_network, "edges", True),
        # The editor maintains nodes when edges are saved, so they are not
        # offered for editing.
        (BundleTypeName.street_network, "nodes", False),
        (BundleTypeName.pt_network_gtfs, "stops", False),
        (BundleTypeName.pt_network_gtfs, "shapes", False),
    ],
)
def test_role_editability(bundle_type, role, expected):
    assert SPECS[bundle_type].role(role).editable is expected


def test_a_role_is_not_editable_until_someone_says_so():
    """Fails closed: a role added later must not accept writes by default."""
    assert RoleSpec(key="whatever", label="Whatever").editable is False
    assert [r.key for r in SPECS[BundleTypeName.pt_network_gtfs].roles if r.editable] == []


# --- artifact bookkeeping --------------------------------------------------


class FakePool:
    """Records the SQL it is handed, so the guarantees can be asserted."""

    def __init__(self, rows=None, execute_result="UPDATE 1"):
        self.calls: list[tuple] = []
        self._rows = rows or []
        self._execute_result = execute_result

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return self._rows[0] if self._rows else None

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self._rows

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return self._execute_result


def _service(pool):
    svc = ToolDatabaseService.__new__(ToolDatabaseService)
    svc.schema = "customer"
    svc.pool = pool
    return svc


async def test_create_artifact_upserts_so_a_rebuild_can_reuse_the_row():
    """(bundle_id, kind) is unique — a plain INSERT would raise on rebuild."""
    svc = _service(FakePool([{"id": ARTIFACT}]))
    await svc.create_artifact(bundle_id=BUNDLE, kind="street_network_graph")
    query = svc.pool.calls[0][0]
    assert "ON CONFLICT (bundle_id, kind)" in query
    assert "DO UPDATE" in query


async def test_artifact_lookup_returns_status_for_a_non_ready_row():
    """The status separates "being updated" from "never built" for the caller."""
    svc = _service(FakePool([{"storage_path": None, "status": "stale"}]))
    row = await svc.get_bundle_artifact(BUNDLE, "street_network_graph")
    assert row["status"] == "stale"
    assert "status = 'ready'" not in svc.pool.calls[0][0]


@pytest.mark.parametrize(
    ("result", "published"), [("UPDATE 1", True), ("UPDATE 0", False)]
)
async def test_publish_is_guarded_by_the_revision_it_built_from(result, published):
    """A build overtaken by a later save must not publish its output."""
    svc = _service(FakePool(execute_result=result))
    assert (
        await svc.publish_artifact_if_current(
            artifact_id=ARTIFACT,
            bundle_id=BUNDLE,
            built_revision=7,
            storage_path=f"{BUNDLE}/street_network_graph.tar",
            size=123,
        )
        is published
    )
    # The comparison lives in the WHERE clause, so there is no window between
    # checking and writing.
    query = svc.pool.calls[0][0]
    assert "layers_revision = $5" in query


async def test_revision_and_member_helpers_read_what_a_rebuild_needs():
    svc = _service(FakePool([{"layers_revision": 3}]))
    assert await svc.get_bundle_revision(BUNDLE) == 3

    svc = _service(FakePool([{"layers_revision": 8}]))
    assert await svc.bump_bundle_revision(BUNDLE) == 8

    svc = _service(FakePool([{"role": "edges", "layer_id": "l-edges"}]))
    assert (await svc.list_bundle_layers(BUNDLE))[0]["role"] == "edges"


# --- the rebuild tool ------------------------------------------------------


def test_rebuild_requires_a_bundle_id():
    with pytest.raises(ValidationError):
        BundleArtifactRebuildParams(user_id=USER)
    assert BundleArtifactRebuildParams(user_id=USER, bundle_id="b1").bundle_id == "b1"


def test_import_and_rebuild_build_artifacts_through_one_code_path():
    """Two callers, one implementation: an edit is built exactly as an import is."""
    assert issubclass(BundleArtifactRebuildRunner, BundleArtifactBuildMixin)
    assert issubclass(BundleImportRunner, BundleArtifactBuildMixin)


def test_a_layer_based_build_without_members_is_refused():
    with pytest.raises(ValueError, match="member layers"):
        BundleArtifactBuildMixin().export_member_layers(
            user_id=USER, members=[], workdir="/tmp"
        )


def test_the_rebuild_tool_is_dispatchable():
    entry = next(
        (t for t in TOOL_REGISTRY if t.name == "bundle_artifact_rebuild"), None
    )
    assert entry is not None
    assert entry.windmill_path == "f/goat/tools/bundle_artifact_rebuild"
    assert entry.toolbox_hidden is True
