# Standard library imports
from typing import Any, List, Tuple, Union
from uuid import UUID

# Third party imports
from fastapi import HTTPException, status
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models._link_model import LayerProjectGroup, LayerProjectLink
from core.db.models.layer import Layer
from core.db.models.project import Project
from core.schemas.project import (
    IFeatureStandardProjectRead,
    IFeatureStreetNetworkProjectRead,
    IFeatureToolProjectRead,
    IRasterProjectRead,
    ITableProjectRead,
    layer_type_mapping_read,
    layer_type_mapping_update,
)

# Local application imports
from .base import CRUDBase


async def make_room_at_top(
    async_session: AsyncSession, project_id: UUID, count: int
) -> None:
    """Push everything already in a project down by ``count`` positions.

    Groups and layers share one tree-wide order sequence, so both have to move
    or the new rows land in among the old ones instead of above them.
    """
    if count <= 0:
        return
    for model in (LayerProjectLink, LayerProjectGroup):
        await async_session.execute(
            sql_update(model)
            .where(model.project_id == project_id)
            .values(order=model.order + count)
        )
    await async_session.commit()


def initial_link_properties(
    existing_link: Any | None, layer: Any
) -> dict[str, Any] | None:
    """What a new project-layer link starts out looking like.

    When the layer is already in this project the style comes off the link
    already there, so a duplicate matches what the user made rather than
    snapping back to the dataset's default.

    `visibility` rides in that same blob and is deliberately NOT copied: it is
    view state, not style. Adding a dataset you had hidden would otherwise give
    you a second copy you also cannot see, which reads as the add having failed
    — and the one thing you certainly meant by adding a layer is to look at it.
    """
    if existing_link is None:
        return layer.properties
    properties = existing_link.properties
    if not isinstance(properties, dict):
        return properties
    # Copied, not mutated: the link already in the project keeps its own state.
    return {**properties, "visibility": True}


class CRUDLayerProject(CRUDBase):
    async def layer_projects_to_schemas(
        self,
        async_session: AsyncSession,
        layers_project: List[Tuple[Layer, LayerProjectLink]],
    ) -> List[
        IFeatureStandardProjectRead
        | IFeatureToolProjectRead
        | IFeatureStreetNetworkProjectRead
        | ITableProjectRead
        | IRasterProjectRead
    ]:
        """Convert layer projects to schemas."""
        layer_projects_schemas = []

        # Loop through layer and layer projects
        for layer_project_tuple in layers_project:
            layer = layer_project_tuple[0]
            layer_project_model = layer_project_tuple[1]

            # Get layer type
            if layer.feature_layer_type is not None:
                layer_type = layer.type + "_" + layer.feature_layer_type
            else:
                layer_type = layer.type

            layer_dict = layer.model_dump()
            # Delete id from layer
            del layer_dict["id"]
            # Update layer with layer project
            layer_dict.update(layer_project_model.model_dump())
            # Kept apart from the tile-busting value below: this one answers
            # "how current is the data", which restyling must not change.
            layer_dict["dataset_updated_at"] = layer.updated_at
            # The link's fields win above, including updated_at — but the map
            # keys its tile source on that value, and materialize finishing
            # bumps only the LAYER's. Take the later of the two so either
            # side changing refetches the tiles.
            if layer.updated_at and layer_dict.get("updated_at"):
                layer_dict["updated_at"] = max(
                    layer.updated_at, layer_dict["updated_at"]
                )
            # The link froze a copy of other_properties at add time (that is
            # what makes style per-project), but a catalog layer's materialize
            # lifecycle is layer-global and moves on afterwards — serve those
            # keys live from the layer or pending would never clear.
            if layer.catalog_external_uid is not None and layer.other_properties:
                merged = dict(layer_dict.get("other_properties") or {})
                for key in ("catalog_item", "catalog_materialize"):
                    if key in layer.other_properties:
                        merged[key] = layer.other_properties[key]
                layer_dict["other_properties"] = merged
            layer_project: Union[
                IFeatureStandardProjectRead
                | IFeatureToolProjectRead
                | IFeatureStreetNetworkProjectRead
                | ITableProjectRead
                | IRasterProjectRead
            ] = layer_type_mapping_read[layer_type](**layer_dict)

            # Write into correct schema
            # Note: total_count and filtered_count are fetched on-demand via geoapi
            layer_projects_schemas.append(layer_project)

        return layer_projects_schemas

    async def get_layers(
        self,
        async_session: AsyncSession,
        project_id: UUID,
    ) -> List[
        IFeatureStandardProjectRead
        | IFeatureToolProjectRead
        | IFeatureStreetNetworkProjectRead
        | ITableProjectRead
        | IRasterProjectRead
    ]:
        """Get all layers from a project, sorted by layer_order.

        Layers are returned in the order defined by the project's layer_order
        array. Layers at the beginning of layer_order appear first (on top in UI).
        """
        # Get project to retrieve layer_order
        project = await CRUDBase(Project).get(async_session, id=project_id)
        layer_order = project.layer_order or []

        # Get all layers from project
        query = select(Layer, LayerProjectLink).where(
            LayerProjectLink.project_id == project_id,
            Layer.id == LayerProjectLink.layer_id,
        )

        # Get all layers from project
        layer_projects_to_schemas = await self.layer_projects_to_schemas(
            async_session,
            await self.get_multi(
                async_session,
                query=query,
            ),
        )

        # Sort layers by layer_order array (first in array = first in result = on top)
        if layer_order:
            order_map = {
                layer_project_id: idx
                for idx, layer_project_id in enumerate(layer_order)
            }
            layer_projects_to_schemas.sort(
                key=lambda layer: order_map.get(layer.id, len(layer_order))
            )

        return layer_projects_to_schemas

    async def get_by_ids(
        self, async_session: AsyncSession, ids: list[int]
    ) -> List[
        IFeatureStandardProjectRead
        | IFeatureToolProjectRead
        | IFeatureStreetNetworkProjectRead
        | ITableProjectRead
        | IRasterProjectRead
    ]:
        """Get all layer projects links by the ids"""

        # Get all layers from project by id
        query = (
            select(Layer, LayerProjectLink)
            .where(
                LayerProjectLink.id.in_(ids),
            )
            .where(
                Layer.id == LayerProjectLink.layer_id,
            )
        )

        # Get all layers from project
        layer_projects = await self.layer_projects_to_schemas(
            async_session,
            await self.get_multi(
                async_session,
                query=query,
            ),
        )
        return layer_projects

    async def count_by_project(
        self, async_session: AsyncSession, project_id: UUID
    ) -> int:
        """How many layers this project already holds."""
        result = await async_session.execute(
            select(func.count())
            .select_from(LayerProjectLink)
            .where(LayerProjectLink.project_id == project_id)
        )
        return int(result.scalar_one())

    async def create(
        self,
        async_session: AsyncSession,
        project_id: UUID,
        layer_ids: List[UUID],
        group_id: int | None = None,
        start_order: int | None = None,
    ) -> List[BaseModel]:
        """Create a link between a project and a layer.

        When ``group_id`` is given, the new links are placed into that layer
        group (used when adding a bundle's member layers into its group).

        ``order`` is a position in the project's single tree-wide sequence — the
        layer panel writes it by flattening the whole tree. New links go to the
        top of that sequence, whatever they are: the project is pushed down to
        make room for them. ``start_order`` overrides this for a caller that has
        already made its own room and needs the links at a known position, which
        is how a bundle's members end up directly under their group header.
        """

        # Drop duplicates but keep the caller's order: it fixes the order the
        # links are created in, and so their order in the project.
        layer_ids = list(dict.fromkeys(layer_ids))

        # Get number of layers in project
        layer_projects = await self.get_multi(
            async_session,
            query=select(LayerProjectLink).where(
                LayerProjectLink.project_id == project_id
            ),
        )

        # Check if maximum number of layers in project is reached. In case layer_project is empty just go on.
        if layer_projects != []:
            if len(layer_projects) + len(layer_ids) >= 300:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Maximum number of layers in project reached",
                )

        layers = await CRUDBase(Layer).get_multi(
            async_session,
            query=select(Layer).where(Layer.id.in_(layer_ids)),
        )

        if len(layers) != len(layer_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or several Layers were not found",
            )

        # Everything new goes on top, so the project moves down first. Skipped
        # ids leave a gap in the sequence, which the panel closes the next time
        # the tree is reordered.
        if start_order is None:
            await make_room_at_top(async_session, project_id, len(layer_ids))
            start_order = 0

        # Define array for layer project ids
        layer_project_ids = []

        # Iterate layer_ids rather than the query result: the SELECT ... IN
        # returns rows in whatever order the database chose.
        layers_by_id = {row[0].id: row[0] for row in layers}

        # Create link between project and layer
        for position, layer_id in enumerate(layer_ids):
            # An id with no accessible layer row is skipped, not a 500: the
            # SELECT ... IN above simply won't have returned it.
            layer = layers_by_id.get(layer_id)
            if layer is None:
                continue

            # Check if layer with same name and ID already exists in project. Then the layer should be duplicated with a new name.
            layer_name = layer.name
            # Find existing project-layer link to copy style from (if duplicating within same project)
            existing_link = None
            if layer_projects != []:
                for lp in layer_projects:
                    if lp[0].layer_id == layer.id:
                        existing_link = lp[0]
                        break
                if layer.name in [
                    layer_project[0].name for layer_project in layer_projects
                ]:
                    layer_name = "Copy from " + layer.name

            properties = initial_link_properties(existing_link, layer)
            other_properties = (
                existing_link.other_properties
                if existing_link
                else layer.other_properties
            )

            # Create layer project link
            layer_project = LayerProjectLink(
                project_id=project_id,
                layer_id=layer.id,
                name=layer_name,
                properties=properties,
                other_properties=other_properties,
                layer_project_group_id=group_id,
                order=start_order + position,
            )

            # Add to database
            layer_project = await CRUDBase(LayerProjectLink).create(
                async_session,
                obj_in=layer_project.model_dump(),
            )
            layer_project_ids.append(layer_project.id)

        # Get project to update layer order
        project = await CRUDBase(Project).get(async_session, id=project_id)
        # Legacy sequence, kept in step with the order column: it only decides
        # the API response's order, which the layer panel re-sorts anyway.
        layer_order = layer_project_ids + list(project.layer_order or [])

        # Update project layer order
        project = await CRUDBase(Project).update(
            async_session,
            db_obj=project,
            obj_in={"layer_order": layer_order},
        )
        layers = await self.get_by_ids(async_session, ids=layer_project_ids)
        return layers

    async def update(
        self,
        async_session: AsyncSession,
        id: int,
        layer_in: dict,
    ) -> (
        IFeatureStandardProjectRead
        | IFeatureToolProjectRead
        | IFeatureStreetNetworkProjectRead
        | ITableProjectRead
        | IRasterProjectRead
    ):
        """Update a link between a project and a layer"""

        # Get layer project
        layer_project_old = await self.get(
            async_session,
            id=id,
        )
        layer_id = layer_project_old.layer_id

        # Get base layer object
        layer = await CRUDBase(Layer).get(async_session, id=layer_id)
        layer_dict = layer.dict()

        # Get right schema for respective layer type
        if layer.feature_layer_type is not None:
            model_type_update = layer_type_mapping_update.get(
                layer.type + "_" + layer.feature_layer_type
            )
            model_type_read = layer_type_mapping_read.get(
                layer.type + "_" + layer.feature_layer_type
            )
        else:
            model_type_update = layer_type_mapping_update.get(layer.type)
            model_type_read = layer_type_mapping_read.get(layer.type)

        # Parse and validate the data against the model
        try:
            layer_in = TypeAdapter(model_type_update).validate_python(layer_in)
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e),
            )

        if layer_project_old is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Layer project not found"
            )

        # Update layer project
        layer_project = await CRUDBase(LayerProjectLink).update(
            async_session,
            db_obj=layer_project_old,
            obj_in=layer_in,
        )
        layer_project_dict = layer_project.dict()
        del layer_dict["id"]
        # Update layer
        layer_dict.update(layer_project_dict)
        layer_project = model_type_read(**layer_dict)
        # Note: total_count and filtered_count are fetched on-demand via geoapi
        return layer_project


layer_project = CRUDLayerProject(LayerProjectLink)
