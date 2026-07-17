import logging

import aiohttp
from core.core.config import settings
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


async def execute_process(
    *,
    process_id: str,
    inputs: dict,
    access_token: str,
) -> str:
    """Trigger an OGC process (a Windmill job) via the processes service.

    Returns the submitted job id. Raises HTTPException on failure so callers can
    surface the problem (and run any compensating action, e.g. marking a created
    record failed). Callers that want best-effort behaviour should catch it (see
    ``delete_layers_via_geoapi``).
    """
    if not settings.GOAT_GEOAPI_HOST:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processes service (GOAT_GEOAPI_HOST) is not configured",
        )

    url = f"{settings.GOAT_GEOAPI_HOST}/processes/{process_id}/execution"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json={"inputs": inputs}, headers=headers
        ) as response:
            if response.status in (200, 201):
                result = await response.json()
                job_id = result.get("jobID", "")
                logger.info("Submitted process %s as job %s", process_id, job_id)
                return job_id
            error_text = await response.text()
            logger.error(
                "Failed to submit process %s: %s %s",
                process_id,
                response.status,
                error_text,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to start '{process_id}' job",
            )


async def delete_layers_via_geoapi(
    layer_ids: list[str], access_token: str
) -> None:
    """Delete layers' DuckLake tables via the ``layer_delete_multi`` process.

    Best-effort: called after the layers' PostgreSQL records are already gone, so
    a failure here (unconfigured host, processes error) is logged but never
    raised — it must not undo the completed delete.
    """
    if not layer_ids:
        return
    try:
        await execute_process(
            process_id="layer_delete_multi",
            inputs={"layer_ids": layer_ids},
            access_token=access_token,
        )
    except Exception as e:
        logger.warning(
            "DuckLake cleanup for %d layers did not start: %s", len(layer_ids), e
        )
