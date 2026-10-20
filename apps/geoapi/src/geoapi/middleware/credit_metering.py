"""Per-response egress metering: org × layer × service, with bytes /
request count / anonymous count, attributed to the layer owner.

Hot path: one cached org/owner lookup + a few Redis HINCRBYs. Fail-open
everywhere — metering must never break a response. See spec §5/§7/§12.
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)

_COLLECTION_RE = re.compile(r"/collections/([^/]+)")

# Counter hashes expire if the rollup does not drain them, so junk (and a
# stalled rollup) cannot make Redis grow without bound.
_COUNTER_TTL_SECONDS = 7 * 24 * 3600
# Only a delivered body is metered: not HEAD, not redirects, not errors.
_METERED_STATUS = (200, 206)


def _collection_id_from_path(path: str) -> str | None:
    m = _COLLECTION_RE.search(path or "")
    return m.group(1) if m else None


def _normalized_layer_id(collection_id: str) -> str | None:
    """Canonical layer id, so case/dash/urn variants of one layer share one
    counter key; None when the path segment is not a layer id at all."""
    from goatlib.utils.layer import normalize_layer_id

    try:
        return normalize_layer_id(str(UUID(collection_id)))
    except ValueError:  # includes InvalidLayerIdError
        return None


def _service_from_path(path: str) -> str:
    if "/tiles/" in path:
        return "tiles"
    if path.endswith("/download"):
        return "downloads"
    return "features"


def _redis() -> "redis.Redis | None":
    from geoapi.tile_cache import get_redis_client

    return get_redis_client()


async def _resolve_layer_org(collection_id: str) -> tuple[str | None, str | None]:
    """Return (organization_id, owner_user_id) for a collection, or (None, None)."""
    try:
        from geoapi.services.layer_service import layer_service

        meta = await layer_service.get_metadata_by_id(UUID(collection_id))
        if not meta:
            return (None, None)
        return (getattr(meta, "organization_id", None), getattr(meta, "user_id", None))
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.debug("metering: resolve failed for %s (%s)", collection_id, exc)
        return (None, None)


def _record_sync(
    client: "redis.Redis",
    org: str,
    owner: str | None,
    layer: str,
    service: str,
    size: int,
    anonymous: bool,
) -> None:
    key = f"meter:egress:{org}:{layer}:{service}"
    pipe = client.pipeline()
    pipe.hincrby(key, "bytes", size)
    pipe.hincrby(key, "count", 1)
    if anonymous:
        pipe.hincrby(key, "anon_count", 1)
    if owner:
        pipe.hset(key, "owner", owner)
    pipe.expire(key, _COUNTER_TTL_SECONDS)
    pipe.execute()  # type: ignore[no-untyped-call]


async def _record(
    org: str,
    owner: str | None,
    layer: str,
    service: str,
    size: int,
    anonymous: bool,
) -> None:
    client = _redis()
    if not client:
        return
    try:
        await asyncio.to_thread(
            _record_sync, client, org, owner, layer, service, size, anonymous
        )
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.debug("metering: record failed (%s)", exc)


async def _is_over_budget(org_id: str) -> bool:
    client = _redis()
    if not client:
        return False
    try:
        val = await asyncio.to_thread(client.get, f"meter:over_budget:{org_id}")
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.debug("metering: over-budget read failed (%s)", exc)
        return False
    return val in (b"1", "1", 1)


class CreditMeteringMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raw_id = _collection_id_from_path(request.url.path)
        layer_id = _normalized_layer_id(raw_id) if raw_id else None
        org_id, owner_id = (
            await _resolve_layer_org(layer_id) if layer_id else (None, None)
        )

        # Out of credits: downloads stop, viewing does not. Maps and dashboards
        # (tiles, features) keep working, so a published map never goes dark.
        if (
            org_id
            and _service_from_path(request.url.path) == "downloads"
            and await _is_over_budget(org_id)
        ):
            return Response(
                status_code=402,
                content=b"Organization is out of credits for this period.",
            )

        response = await call_next(request)

        if (
            org_id
            and layer_id
            and request.method == "GET"
            and response.status_code in _METERED_STATUS
        ):
            try:
                size = int(response.headers.get("content-length") or 0)
            except (TypeError, ValueError):
                size = 0
            if size > 0:
                service = _service_from_path(request.url.path)
                anonymous = "authorization" not in request.headers
                await _record(org_id, owner_id, layer_id, service, size, anonymous)
        return response
