"""Probes for the dependencies GOAT relies on.

One function per dependency: returns on success, raises on failure. The
runner, the timer and the gauge live in goatobs.health — this package holds
only the probes, because the clients they need (boto3, asyncpg, duckdb) are
already here and must never be added to goatobs.
"""

from goatlib.health.checks.object_storage import (
    check_object_storage,
    probe_object_storage,
)

__all__ = ["check_object_storage", "probe_object_storage"]
