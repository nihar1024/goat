"""Registry of computed column kinds (area, perimeter, length, ...)."""

from goatlib.computed_columns.display_config import (
    AreaDisplayConfig,
    LengthDisplayConfig,
    NumberDisplayConfig,
    PerimeterDisplayConfig,
    StringDisplayConfig,
    get_display_config_model,
    validate_display_config,
)
from goatlib.computed_columns.registry import (
    COMPUTED_KIND_REGISTRY,
    ComputedKind,
    get_computed_kind,
    is_computed_kind,
)

__all__ = [
    "AreaDisplayConfig",
    "COMPUTED_KIND_REGISTRY",
    "ComputedKind",
    "LengthDisplayConfig",
    "NumberDisplayConfig",
    "PerimeterDisplayConfig",
    "StringDisplayConfig",
    "get_computed_kind",
    "get_display_config_model",
    "is_computed_kind",
    "validate_display_config",
]
