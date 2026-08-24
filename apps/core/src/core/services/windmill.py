"""Fire-and-forget Windmill job submission.

Core stays out of job orchestration — processes owns that — but a few things
must be enqueued server-side because they cannot depend on a browser being
open, catalog materialization being the case at hand. This is the minimal
client for exactly that: submit and return, no polling, no job tracking.
"""

import logging
from typing import Any

import httpx
from core.core.config import settings

logger = logging.getLogger(__name__)


async def run_script(script_path: str, args: dict[str, Any]) -> str | None:
    """Submit a Windmill script run; returns the job id, or None on failure.

    Failure is logged, not raised: the callers' state machines treat an
    unenqueued job as "still pending", which a later retry or sweep resolves —
    a user-facing request should not fail because the job queue hiccuped.
    """
    if not (settings.WINDMILL_URL and settings.WINDMILL_TOKEN):
        logger.warning(
            "Windmill is not configured (WINDMILL_URL/WINDMILL_TOKEN); "
            "cannot enqueue %s",
            script_path,
        )
        return None

    url = (
        f"{settings.WINDMILL_URL}/api/w/{settings.WINDMILL_WORKSPACE}"
        f"/jobs/run/p/{script_path}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                json=args,
                headers={"Authorization": f"Bearer {settings.WINDMILL_TOKEN}"},
            )
            response.raise_for_status()
            job_id = response.text.strip()
            logger.info("Enqueued %s as job %s", script_path, job_id)
            return job_id
    except Exception as e:
        logger.error("Failed to enqueue %s: %s", script_path, e)
        return None
