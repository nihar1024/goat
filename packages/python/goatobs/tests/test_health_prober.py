"""The prober loop and what it reports as a gauge.

The gauge carries `component` — the status-page system id — so an alert can
pass it straight through to Alertmanager and the adapter needs no lookup
table to know which row to mark.
"""

import asyncio

import pytest
from goatobs.health.prober import Prober

pytestmark = pytest.mark.unit


def _prober(**kwargs: object) -> Prober:
    async def fine() -> None:
        return None

    async def broken() -> None:
        raise ConnectionError("nope")

    return Prober(
        checks={"object_storage": fine, "keycloak": broken},
        components={"object_storage": ["uploads-exports"], "keycloak": ["login"]},
        interval=0.01,
        timeout=0.5,
        **kwargs,  # type: ignore[arg-type]
    )


async def test_nothing_is_reported_before_the_first_cycle() -> None:
    """An empty gauge is honest: we have not looked yet."""
    assert list(_prober().observe()) == []


async def test_a_cycle_reports_one_observation_per_dependency() -> None:
    prober = _prober()
    await prober.run_once()
    observed = {o.attributes["dependency"]: o.value for o in prober.observe()}
    assert observed == {"object_storage": 1, "keycloak": 0}


async def test_each_observation_carries_its_component() -> None:
    prober = _prober()
    await prober.run_once()
    components = {
        o.attributes["dependency"]: o.attributes["component"] for o in prober.observe()
    }
    assert components == {
        "object_storage": "uploads-exports",
        "keycloak": "login",
    }


async def test_a_dependency_several_systems_rely_on_reports_one_series_each() -> None:
    """Postgres backs the workspace, layer metadata and analyses. One series
    per affected system means a single alert rule grouped by (dependency,
    component) covers every dependency without naming any of them."""

    async def broken() -> None:
        raise ConnectionError("nope")

    prober = Prober(
        checks={"postgres": broken},
        components={"postgres": ["workspace", "map-layers", "analyses"]},
        interval=1.0,
        timeout=1.0,
    )
    await prober.run_once()
    observed = [
        (o.attributes["dependency"], o.attributes["component"], o.value)
        for o in prober.observe()
    ]
    assert observed == [
        ("postgres", "workspace", 0),
        ("postgres", "map-layers", 0),
        ("postgres", "analyses", 0),
    ]


async def test_an_empty_component_list_is_rejected() -> None:
    """A check nothing depends on cannot be routed anywhere."""

    async def fine() -> None:
        return None

    with pytest.raises(ValueError):
        Prober(
            checks={"object_storage": fine},
            components={"object_storage": []},
            interval=1.0,
            timeout=1.0,
        )


async def test_results_are_available_for_a_human_to_read() -> None:
    prober = _prober()
    await prober.run_once()
    failed = [r for r in prober.results if not r.ok]
    assert [r.name for r in failed] == ["keycloak"]
    assert failed[0].error == "ConnectionError"


async def test_a_check_that_explodes_does_not_stop_the_loop() -> None:
    """One bad dependency must not end the prober's life."""
    cycles = 0

    async def counts() -> None:
        nonlocal cycles
        cycles += 1
        raise RuntimeError("always broken")

    prober = Prober(
        checks={"object_storage": counts},
        components={"object_storage": ["uploads-exports"]},
        interval=0.01,
        timeout=0.5,
    )
    task = asyncio.create_task(prober.run_forever())
    await asyncio.sleep(0.06)
    task.cancel()
    assert cycles >= 3


async def test_the_loop_stops_when_cancelled() -> None:
    prober = _prober()
    task = asyncio.create_task(prober.run_forever())
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_dependency_with_no_component_is_rejected_at_construction() -> None:
    """A gauge without a component cannot be routed to a status-page row."""

    async def fine() -> None:
        return None

    with pytest.raises(ValueError):
        Prober(
            checks={"object_storage": fine},
            components={},
            interval=1.0,
            timeout=1.0,
        )
