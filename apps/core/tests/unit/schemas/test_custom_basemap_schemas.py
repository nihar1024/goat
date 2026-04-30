from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from core.schemas.custom_basemap import CustomBasemap


CUSTOM_BASEMAP_ADAPTER = TypeAdapter(CustomBasemap)


def _base_fields() -> dict:
    return {
        "id": str(uuid4()),
        "name": "My basemap",
        "description": None,
        "thumbnail_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def test_vector_custom_basemap_valid():
    data = {**_base_fields(), "type": "vector", "url": "https://example.com/style.json"}
    parsed = CUSTOM_BASEMAP_ADAPTER.validate_python(data)
    assert parsed.type == "vector"
    assert str(parsed.url) == "https://example.com/style.json"


def test_vector_custom_basemap_rejects_invalid_url():
    data = {**_base_fields(), "type": "vector", "url": "not-a-url"}
    with pytest.raises(ValidationError):
        CUSTOM_BASEMAP_ADAPTER.validate_python(data)


def test_raster_custom_basemap_requires_xyz_placeholders():
    data = {
        **_base_fields(),
        "type": "raster",
        "url": "https://example.com/{z}/{x}/{y}.png",
        "attribution": "© Example",
    }
    parsed = CUSTOM_BASEMAP_ADAPTER.validate_python(data)
    assert parsed.type == "raster"
    assert parsed.attribution == "© Example"


def test_raster_custom_basemap_rejects_missing_placeholder():
    data = {
        **_base_fields(),
        "type": "raster",
        "url": "https://example.com/{z}/{x}.png",
    }
    with pytest.raises(ValidationError, match="placeholders"):
        CUSTOM_BASEMAP_ADAPTER.validate_python(data)


def test_solid_custom_basemap_valid():
    data = {**_base_fields(), "type": "solid", "color": "#ff8800"}
    parsed = CUSTOM_BASEMAP_ADAPTER.validate_python(data)
    assert parsed.type == "solid"
    assert parsed.color == "#ff8800"


def test_solid_custom_basemap_rejects_invalid_color():
    data = {**_base_fields(), "type": "solid", "color": "orange"}
    with pytest.raises(ValidationError):
        CUSTOM_BASEMAP_ADAPTER.validate_python(data)


def test_solid_custom_basemap_accepts_alpha_color():
    data = {**_base_fields(), "type": "solid", "color": "#ff8800cc"}
    parsed = CUSTOM_BASEMAP_ADAPTER.validate_python(data)
    assert parsed.color == "#ff8800cc"


def test_unknown_type_rejected():
    data = {**_base_fields(), "type": "wmts", "url": "https://example.com"}
    with pytest.raises(ValidationError):
        CUSTOM_BASEMAP_ADAPTER.validate_python(data)
