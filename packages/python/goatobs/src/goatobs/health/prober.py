"""Run dependency checks on a timer and report each as a gauge.

The gauge is the product, not the endpoint: it is what an alert rule can
fire on, so it has to exist whether or not anyone is looking. Hence a timer
rather than checking on request.

One observation per (dependency, component) pair, because a dependency is
rarely load-bearing for exactly one thing: Postgres backs the workspace,
layer metadata and analyses at once. Emitting the pair means a single alert
rule grouped by those two labels covers every dependency without naming any
of them, so adding a dependency later needs no rule change.

`component` is the status-page system id, so an alert passes it straight
through to Alertmanager and the adapter that writes the incident needs no
lookup table to know which rows to mark.
"""

import asyncio
from collections.abc import Iterable, Mapping, Sequence

import structlog
from opentelemetry import metrics as otel_metrics
from opentelemetry.metrics import CallbackOptions, Observation

from goatobs.health.runner import Check, CheckResult, run_all

logger = structlog.get_logger(__name__)

#: Becomes goat_dependency_up in Prometheus/Mimir.
GAUGE_NAME = "goat.dependency.up"


class Prober:
    """Checks dependencies every `interval` seconds and exposes the last result."""

    def __init__(
        self,
        *,
        checks: Mapping[str, Check],
        components: Mapping[str, Sequence[str]],
        interval: float,
        timeout: float,
    ) -> None:
        # A gauge with no component cannot be routed to a status-page row, so
        # refuse at construction rather than emitting an unusable series.
        unroutable = sorted(name for name in checks if not components.get(name))
        if unroutable:
            raise ValueError(f"no component mapping for: {', '.join(unroutable)}")
        self._checks = checks
        self._components = components
        self._interval = interval
        self._timeout = timeout
        self._results: list[CheckResult] = []

    @property
    def results(self) -> list[CheckResult]:
        """The most recent cycle, for a human reading the endpoint or the logs."""
        return list(self._results)

    async def run_once(self) -> None:
        """One cycle. Never raises: the runner turns failures into results."""
        self._results = await run_all(self._checks, timeout=self._timeout)
        for result in self._results:
            if not result.ok:
                logger.warning(
                    "dependency check failed",
                    dependency=result.name,
                    components=list(self._components[result.name]),
                    error=result.error,
                    latency_ms=result.latency_ms,
                )

    async def run_forever(self) -> None:
        """Loop until cancelled. A failing dependency must not end the prober."""
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop outlives any one cycle
                logger.exception("dependency check cycle failed")
            await asyncio.sleep(self._interval)

    def observe(self, _options: CallbackOptions | None = None) -> Iterable[Observation]:
        """Gauge callback. Empty before the first cycle, which is honest."""
        return [
            Observation(
                1 if result.ok else 0,
                {"dependency": result.name, "component": component},
            )
            for result in self._results
            for component in self._components[result.name]
        ]

    def register_gauge(self) -> None:
        """Attach `observe` to the meter provider goatobs already set up."""
        meter = otel_metrics.get_meter("goatobs.health")
        meter.create_observable_gauge(
            GAUGE_NAME,
            callbacks=[self.observe],
            description="1 when the dependency answered, 0 when it did not",
        )
