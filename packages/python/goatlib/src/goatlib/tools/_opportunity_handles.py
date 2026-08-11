"""Numbered opportunity-layer handles for the workflow canvas.

A canvas edge can only target a named input, never an element of a list, so
heatmaps expose their opportunity layers as up to three numbered handles
instead of the repeatable `opportunities` list.
`workflow_runner.build_tool_inputs` folds them back into that list — together
with the matching `opportunity_{N}_*` config keys — before the tool runs.

Single source of truth for the count, the field names and the declarations, so
the tools carrying these handles cannot drift apart.
"""

from typing import Any

from pydantic import BaseModel, Field

from goatlib.analysis.schemas.ui import ui_field

# How many opportunity layers the canvas offers handles for.
MAX_OPPORTUNITY_LAYERS = 3

NUMBERED_OPPORTUNITY_ID_FIELDS: tuple[str, ...] = tuple(
    f"opportunity_layer_{n}_id" for n in range(1, MAX_OPPORTUNITY_LAYERS + 1)
)
NUMBERED_OPPORTUNITY_FILTER_FIELDS: tuple[str, ...] = tuple(
    f"opportunity_layer_{n}_filter" for n in range(1, MAX_OPPORTUNITY_LAYERS + 1)
)

# Canvas-only plumbing — folded into `opportunities` and never forwarded to the
# analysis layer.
WORKFLOW_ONLY_OPPORTUNITY_FIELDS: frozenset[str] = frozenset(
    NUMBERED_OPPORTUNITY_ID_FIELDS + NUMBERED_OPPORTUNITY_FILTER_FIELDS
)


class NumberedOpportunityLayersMixin(BaseModel):
    """The numbered opportunity handles, hidden from the form.

    They exist to generate input handles on the workflow node; the toolbox form
    uses the repeatable `opportunities` list instead.
    """

    opportunity_layer_1_id: str | None = Field(
        None,
        description="First opportunity layer (connected from workflow)",
        json_schema_extra=ui_field(
            section="opportunities",
            field_order=1,
            widget="layer-selector",
            label_key="opportunity_layer_1",
            hidden=True,
        ),
    )
    opportunity_layer_1_filter: dict[str, Any] | None = Field(
        None,
        description="CQL2-JSON filter for first opportunity layer",
        json_schema_extra=ui_field(section="opportunities", field_order=2, hidden=True),
    )
    opportunity_layer_2_id: str | None = Field(
        None,
        description="Second opportunity layer (connected from workflow)",
        json_schema_extra=ui_field(
            section="opportunities",
            field_order=3,
            widget="layer-selector",
            label_key="opportunity_layer_2",
            hidden=True,
        ),
    )
    opportunity_layer_2_filter: dict[str, Any] | None = Field(
        None,
        description="CQL2-JSON filter for second opportunity layer",
        json_schema_extra=ui_field(section="opportunities", field_order=4, hidden=True),
    )
    opportunity_layer_3_id: str | None = Field(
        None,
        description="Third opportunity layer (connected from workflow)",
        json_schema_extra=ui_field(
            section="opportunities",
            field_order=5,
            widget="layer-selector",
            label_key="opportunity_layer_3",
            hidden=True,
        ),
    )
    opportunity_layer_3_filter: dict[str, Any] | None = Field(
        None,
        description="CQL2-JSON filter for third opportunity layer",
        json_schema_extra=ui_field(section="opportunities", field_order=6, hidden=True),
    )
