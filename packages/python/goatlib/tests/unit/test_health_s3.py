"""The object-storage probe.

It writes, reads back and deletes, because that is what an upload does. A
HEAD on the bucket would have stayed green through the 25 August Hetzner
outage: the endpoint answered while the buckets behind it were inaccessible.
"""

from typing import Any

import pytest
from goatlib.health.checks.object_storage import probe_object_storage

pytestmark = pytest.mark.unit


class FakeS3:
    """Records the calls a probe makes, and can be told to fail one of them."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[str] = []

    def put_object(self, **_: Any) -> None:
        self._record("put_object")

    def get_object(self, **_: Any) -> dict[str, Any]:
        self._record("get_object")
        return {"Body": _Body(b"ok")}

    def delete_object(self, **_: Any) -> None:
        self._record("delete_object")

    def _record(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_on == name:
            raise ConnectionError(f"{name} unavailable")


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


def test_a_healthy_probe_writes_reads_then_deletes() -> None:
    client = FakeS3()
    probe_object_storage(client, bucket="goat", key=".healthz/probe")
    assert client.calls == ["put_object", "get_object", "delete_object"]


@pytest.mark.parametrize("failing", ["put_object", "get_object"])
def test_a_failure_propagates_so_the_runner_records_it(failing: str) -> None:
    client = FakeS3(fail_on=failing)
    with pytest.raises(ConnectionError):
        probe_object_storage(client, bucket="goat", key=".healthz/probe")


def test_the_probe_object_is_always_cleaned_up_even_when_the_read_fails() -> None:
    """Otherwise a flaky read leaves a probe object behind on every cycle."""
    client = FakeS3(fail_on="get_object")
    with pytest.raises(ConnectionError):
        probe_object_storage(client, bucket="goat", key=".healthz/probe")
    assert "delete_object" in client.calls


def test_a_write_that_reads_back_wrong_is_a_failure() -> None:
    """Reachable but returning the wrong bytes is not health."""

    class WrongBytes(FakeS3):
        def get_object(self, **_: Any) -> dict[str, Any]:
            self.calls.append("get_object")
            return {"Body": _Body(b"something else")}

    with pytest.raises(ValueError):
        probe_object_storage(WrongBytes(), bucket="goat", key=".healthz/probe")
