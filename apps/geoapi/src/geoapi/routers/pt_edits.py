"""Saving the Explorer's edits to a public transport (GTFS) bundle.

The Explorer edits a bundle in the browser, on its own copy, and saves once:
``POST /bundles/{id}/changes`` with the revision it started from and the
change set — rows of the bundle's GTFS tables, keyed by GTFS ids
(``goatlib.bundles.explorer.changeset``). This is the only way a GTFS member
is written: the per-feature endpoints refuse bundle members, and no GTFS role
is ``editable`` (that flag opens the generic feature editor, which knows
nothing of trips and stop times).

One save, all or nothing:

1. The caller must be allowed to write the bundle (``customer.can``, the rule
   its artifact rebuild asks).
2. In one Postgres transaction, the bundle's advisory lock is taken
   exclusively and its ``layers_revision`` moved on from the one the client
   started from — or 409 if somebody saved first.
3. Inside that, the change set is applied in one DuckLake transaction and the
   bundle re-checked; a malformed set is a 400, one that would leave an ERROR
   a 422 with the notices. Either rolls back both transactions, so the
   revision is untouched.
4. Postgres commits only after DuckLake has. An Explorer snapshot build, which
   reads the revision and the data under the same lock taken shared, can never
   pair the new revision with the old data.

Then, outside the transaction: the written layers' tile caches are dropped,
and the bundle's artifacts (and the bundles built from it) are rebuilt. The
next manifest request names the new revision, so the Explorer's next load is
the saved bundle.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from goatlib.bundles.explorer.changeset import (
    ROLE_KEYS,
    Applied,
    ChangeSet,
    ChangeSetError,
    ChangeSetIntegrityError,
    apply_changeset,
)
from goatlib.bundles.locks import bundle_layers_lock_key_sql
from pydantic import BaseModel, Field

from geoapi.dependencies import LayerInfo, get_layer_info_sync
from geoapi.deps.auth import get_user_id
from geoapi.ducklake_write import ducklake_write_manager
from geoapi.routers.bundle_edits import dispatch_dependent_rebuilds, dispatch_rebuild
from geoapi.routers.explorer import _bundle
from geoapi.routers.features_write import (
    _invalidate_caches_and_pmtiles,
    _load_field_config,
)
from geoapi.services.bundle_edit_service import _derived
from geoapi.services.layer_service import layer_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bundles", tags=["Explorer"])

T = TypeVar("T")

#: The members a save reads or writes: the editable tables, and the lines the
#: map draws, which the save keeps in step.
_ROLES = (*ROLE_KEYS, "shape_lines")
#: Members whose rows carry a geometry, so a write fills its derived columns.
_GEOMETRY_ROLES = ("stops", "shape_lines")


class ChangesRequest(BaseModel):
    base_revision: int = Field(
        ..., ge=0, description="The revision the edits start from"
    )
    changes: ChangeSet


class ChangesResponse(BaseModel):
    revision: int
    rows: dict[str, dict[str, int]]
    warnings: list[dict[str, Any]]
    rebuild_job_id: str | None


async def _authorize_write(bundle_id: UUID, user_id: UUID) -> None:
    if not await layer_service.user_can_write_bundle(bundle_id, user_id):
        # One answer for "not there" and "not yours", as everywhere else.
        raise HTTPException(
            status_code=403, detail="This bundle is not yours to change."
        )


async def _within_lock(
    bundle_id: UUID, base_revision: int, write: Callable[[], Awaitable[T]]
) -> tuple[int, T]:
    """Run ``write`` holding the bundle's lock, with the revision moved on
    from ``base_revision``; both undone if ``write`` raises."""
    pool = layer_service._pool
    if not pool:
        raise HTTPException(status_code=503, detail="Database pool not initialized")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"SELECT pg_advisory_xact_lock({bundle_layers_lock_key_sql('$1')})",
                str(bundle_id),
            )
            revision = await conn.fetchval(
                """
                UPDATE customer.bundle
                SET layers_revision = layers_revision + 1, updated_at = NOW()
                WHERE id = $1::uuid AND layers_revision = $2 AND deleted_at IS NULL
                RETURNING layers_revision
                """,
                bundle_id,
                base_revision,
            )
            if revision is None:
                current = await conn.fetchval(
                    "SELECT layers_revision FROM customer.bundle "
                    "WHERE id = $1::uuid AND deleted_at IS NULL",
                    bundle_id,
                )
                if current is None:
                    raise HTTPException(status_code=404, detail="No such bundle")
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": (
                            "This network was saved by someone else while you were "
                            f"editing (revision {current}, you started from "
                            f"{base_revision})."
                        ),
                        "revision": int(current),
                    },
                )
            result = await write()
            return int(revision), result


def _apply_sync(
    members: dict[str, LayerInfo],
    changes: ChangeSet,
    configs: dict[str, dict[str, Any]],
) -> Applied:
    """Apply the change set in one DuckLake transaction. Runs in a thread."""

    def derived(role: str, columns: Any, geom_sql: str) -> list[tuple[str, str]]:
        # The columns a layer derives from its geometry, spelled as every
        # bundle write spells them (bbox, computed columns), minus geometry
        # itself, which the change set writes.
        return [
            (name, sql)
            for name, sql in _derived(columns, geom_sql, configs.get(role))
            if name != "geometry"
        ]

    tables = {role: info.full_table_name for role, info in members.items()}
    with ducklake_write_manager.connection() as con:
        con.execute("BEGIN")
        try:
            applied = apply_changeset(con, tables, changes, derived)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return applied


@router.post(
    "/{bundle_id}/changes",
    summary="Save the Explorer's edits",
    response_model=ChangesResponse,
)
async def save_changes(
    bundle_id: UUID,
    body: ChangesRequest,
    request: Request,
    user_id: UUID = Depends(get_user_id),
) -> ChangesResponse:
    bundle = await _bundle(bundle_id)
    await _authorize_write(bundle_id, user_id)

    loop = asyncio.get_running_loop()
    members: dict[str, LayerInfo] = {}
    for role in _ROLES:
        layer_id = bundle["members"].get(role)
        if layer_id:
            members[role] = await loop.run_in_executor(
                None, get_layer_info_sync, str(layer_id)
            )
    configs = {
        role: await _load_field_config(members[role])
        for role in _GEOMETRY_ROLES
        if role in members
    }

    async def write() -> Applied:
        try:
            return await loop.run_in_executor(
                None, _apply_sync, members, body.changes, configs
            )
        except ChangeSetIntegrityError as e:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "The changes would leave the network invalid.",
                    "notices": [n.as_dict() for n in e.notices],
                },
            )
        except ChangeSetError as e:
            raise HTTPException(status_code=400, detail=str(e))

    revision, applied = await _within_lock(bundle_id, body.base_revision, write)

    # Once per written layer, and the drawn lines with them.
    written = set(applied.rows) | (
        {"shape_lines"} if "shape_lines" in members else set()
    )
    for role in sorted(written & set(members)):
        await _invalidate_caches_and_pmtiles(members[role])

    authorization = request.headers.get("Authorization")
    rebuild_job_id = await dispatch_rebuild(str(bundle_id), authorization)
    await dispatch_dependent_rebuilds(str(bundle_id), authorization)
    logger.info(
        "Bundle %s saved from the Explorer at revision %d: %s",
        bundle_id,
        revision,
        applied.rows,
    )
    return ChangesResponse(
        revision=revision,
        rows=applied.rows,
        warnings=[n.as_dict() for n in applied.warnings],
        rebuild_job_id=rebuild_job_id,
    )
