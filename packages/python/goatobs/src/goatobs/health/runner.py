"""Run dependency checks concurrently, with a hard timeout on each.

A check is a coroutine that returns on success and raises on failure. It
does not retry: retrying inside a probe hides the flakiness that matters —
if object storage fails one request in five, users are seeing failures, and
a probe that quietly succeeds on the third attempt reports "up" and teaches
you nothing. The tolerance belongs in the alert rule, which can smooth over
a window and be retuned without redeploying anything.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

# Returns on success, raises on failure. That is the whole contract.
Check = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class CheckResult:
    """What one probe of one dependency found."""

    name: str
    ok: bool
    latency_ms: int
    #: Exception class name only. This can end up on an unauthenticated
    #: endpoint, and an exception message may carry a connection string.
    error: str | None = None


async def run_check(name: str, check: Check, *, timeout: float) -> CheckResult:
    """Run one check, converting any failure into a result rather than raising."""
    started = time.perf_counter()
    try:
        await asyncio.wait_for(check(), timeout=timeout)
    except TimeoutError:
        # A hung dependency is a failure, not a reason to hang the prober.
        return CheckResult(
            name=name,
            ok=False,
            latency_ms=_elapsed_ms(started),
            error="TimeoutError",
        )
    except BaseException as exc:  # noqa: BLE001 - a probe must never propagate
        return CheckResult(
            name=name,
            ok=False,
            latency_ms=_elapsed_ms(started),
            error=type(exc).__name__,
        )
    return CheckResult(name=name, ok=True, latency_ms=_elapsed_ms(started))


async def run_all(
    checks: Mapping[str, Check],
    *,
    timeout: float,
) -> list[CheckResult]:
    """Run every check at once, so one slow dependency cannot delay the rest."""
    return list(
        await asyncio.gather(
            *(run_check(name, check, timeout=timeout) for name, check in checks.items())
        )
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
