"""The check runner: isolation, timeouts, and honest reporting.

A probe reports facts. It never retries and never smooths — hiding a
transient failure hides the flakiness that matters, and the alert rules
apply the tolerance instead.
"""

import asyncio

import pytest
from goatobs.health import CheckResult, run_all, run_check

pytestmark = pytest.mark.unit


async def test_a_check_that_returns_is_ok() -> None:
    async def fine() -> None:
        return None

    result = await run_check("postgres", fine, timeout=1.0)
    assert result.ok is True
    assert result.error is None
    assert result.name == "postgres"


async def test_a_check_that_raises_is_recorded_as_failed() -> None:
    async def broken() -> None:
        raise ConnectionError("nope")

    result = await run_check("object_storage", broken, timeout=1.0)
    assert result.ok is False
    assert result.error == "ConnectionError"


async def test_only_the_exception_class_is_reported() -> None:
    """The endpoint has no auth, so a message could leak a connection string."""

    async def leaky() -> None:
        raise ConnectionError("postgres://user:hunter2@db.internal:5432/goat")

    result = await run_check("postgres", leaky, timeout=1.0)
    assert result.error == "ConnectionError"
    assert "hunter2" not in str(result)


async def test_a_hanging_check_times_out_rather_than_blocking_forever() -> None:
    async def hangs() -> None:
        await asyncio.sleep(30)

    result = await run_check("object_storage", hangs, timeout=0.05)
    assert result.ok is False
    assert result.error == "TimeoutError"


async def test_latency_is_measured() -> None:
    async def slow() -> None:
        await asyncio.sleep(0.05)

    result = await run_check("redis", slow, timeout=1.0)
    assert result.latency_ms >= 40


async def test_one_failing_check_does_not_affect_the_others() -> None:
    async def fine() -> None:
        return None

    async def broken() -> None:
        raise RuntimeError("boom")

    async def hangs() -> None:
        await asyncio.sleep(30)

    results = await run_all(
        {"a": fine, "b": broken, "c": hangs, "d": fine},
        timeout=0.05,
    )
    by_name = {r.name: r for r in results}
    assert by_name["a"].ok is True
    assert by_name["b"].ok is False
    assert by_name["c"].ok is False
    assert by_name["d"].ok is True


async def test_checks_run_concurrently_not_one_after_another() -> None:
    """Four 100ms checks must take ~100ms, not ~400ms."""

    async def slow() -> None:
        await asyncio.sleep(0.1)

    started = asyncio.get_running_loop().time()
    await run_all({f"c{i}": slow for i in range(4)}, timeout=2.0)
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 0.3


async def test_result_is_immutable() -> None:
    result = CheckResult(name="postgres", ok=True, latency_ms=3)
    with pytest.raises(Exception):
        result.ok = False  # type: ignore[misc]
