"""Probe object storage the way an upload uses it.

A HEAD on the bucket is not enough. During the 25 August 2026 Hetzner
outage the endpoint answered normally while the buckets behind it were
inaccessible, so a HEAD-based probe would have reported healthy for the
whole 21 hours. Writing, reading back and deleting exercises the path a
real upload takes.

Affordable because this runs in ONE prober rather than in every pod: two
probes a minute in total, whatever the replica count.
"""

import asyncio
from typing import Any

_PAYLOAD = b"ok"


def probe_object_storage(client: Any, *, bucket: str, key: str) -> None:
    """Write, read back, delete. Raises if any step fails or the bytes differ."""
    try:
        client.put_object(Bucket=bucket, Key=key, Body=_PAYLOAD)
        response = client.get_object(Bucket=bucket, Key=key)
        got = response["Body"].read()
        if got != _PAYLOAD:
            # Reachable but returning the wrong bytes is not health.
            raise ValueError("probe object read back with unexpected contents")
    finally:
        # Always, even when the read failed — otherwise a flaky read leaves a
        # probe object behind on every cycle.
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except Exception:  # noqa: BLE001 - cleanup must not mask the real error
            pass


async def check_object_storage(client: Any, *, bucket: str, key: str) -> None:
    """Async wrapper: boto3 is synchronous and would block the event loop."""
    await asyncio.to_thread(probe_object_storage, client, bucket=bucket, key=key)
