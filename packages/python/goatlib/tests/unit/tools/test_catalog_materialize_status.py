"""A materialize job that cannot even start must say so in the layer's status."""

from unittest.mock import AsyncMock, patch

import pytest
from goatlib.tools.catalog_materialize import (
    CatalogMaterializeParams,
    CatalogMaterializeRunner,
)


@pytest.mark.parametrize(
    ("layer", "expected_error"),
    [
        (
            {
                "type": "raster",
                "other_properties": {"catalog_item": {"parquet_url": "x"}},
            },
            "No materialize handler",
        ),
        (
            {"type": "feature", "other_properties": {"catalog_item": {}}},
            "has no parquet_url",
        ),
    ],
)
def test_input_errors_land_as_failed_not_pending(
    layer: dict, expected_error: str
) -> None:
    """Raising past the status writes left the layer at `pending` forever, the
    web polling it, and core's heal re-running the same doomed job on every
    re-add."""
    runner = CatalogMaterializeRunner()
    runner.settings = object()  # only checked for None before the work starts
    statuses: list[tuple[str, dict | None]] = []

    async def fake_set_status(
        layer_id: str, status: str, extra: dict | None = None
    ) -> None:
        statuses.append((status, extra))

    with (
        patch.object(runner, "_load_layer", AsyncMock(return_value=layer)),
        patch.object(runner, "_set_status", side_effect=fake_set_status),
        pytest.raises(ValueError, match=expected_error),
    ):
        runner.run(
            CatalogMaterializeParams(
                layer_id="3fa85f64-5717-4562-b3fc-2c963f66afa6", user_id="u"
            )
        )

    assert statuses, "no status was written at all"
    status, extra = statuses[-1]
    assert status == "failed"
    assert expected_error.split()[0] in (extra or {}).get("error", "")
