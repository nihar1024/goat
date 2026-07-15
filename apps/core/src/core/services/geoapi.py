import logging

import aiohttp
from core.core.config import settings

logger = logging.getLogger(__name__)


async def delete_layers_via_geoapi(
    layer_ids: list[str], user_id: str, access_token: str
) -> None:
    """Delete layers' DuckLake tables via the GeoAPI ``layer_delete_multi`` process.

    Triggers a single Windmill job to drop the DuckLake tables for all given
    layers. Called after the layers' PostgreSQL records have been removed (their
    metadata is gone; this cleans up the underlying data).

    Args:
        layer_ids: Layer UUIDs to delete (only feature/table layers have tables).
        user_id: Owner of the layers.
        access_token: Bearer token for authentication.
    """
    if not layer_ids:
        return

    if not settings.GOAT_GEOAPI_HOST:
        logger.warning(
            "GOAT_GEOAPI_HOST not configured, skipping DuckLake cleanup for %d layers",
            len(layer_ids),
        )
        return

    geoapi_url = f"{settings.GOAT_GEOAPI_HOST}/processes/layer_delete_multi/execution"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        try:
            payload = {"inputs": {"layer_ids": layer_ids}}
            async with session.post(
                geoapi_url, json=payload, headers=headers
            ) as response:
                if response.status in (200, 201):
                    result = await response.json()
                    job_id = result.get("jobID", "unknown")
                    logger.info(
                        "Submitted layer_delete_multi job %s for %d layers",
                        job_id,
                        len(layer_ids),
                    )
                else:
                    error_text = await response.text()
                    logger.warning(
                        "Failed to submit layer_delete_multi for %d layers: %s %s",
                        len(layer_ids),
                        response.status,
                        error_text,
                    )
        except Exception as e:
            logger.warning(
                "Error submitting layer_delete_multi for %d layers: %s",
                len(layer_ids),
                e,
            )
