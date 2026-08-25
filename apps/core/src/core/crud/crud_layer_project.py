# Standard library imports
from typing import List, Tuple, Union
from uuid import UUID

# Third party imports
from fastapi import HTTPException, status
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models._link_model import LayerProjectLink
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

    async def create(
        self,
        async_session: AsyncSession,
        project_id: UUID,
        layer_ids: List[UUID],
        group_id: int | None = None,
        start_order: int | None = None,
        append_to_layer_order: bool = False,
    ) -> List[BaseModel]:
        """Create a link between a project and a layer.

        When ``group_id`` is given, the new links are placed into that layer
        group (used when adding a bundle's member layers into its group).

        ``order`` is a position in the project's single tree-wide sequence — the
        layer panel writes it by flattening the whole tree — so links added
        outside the panel have to be given one, or they all land on 0 and tie.
        ``start_order`` numbers the new links from there in ``layer_ids`` order;
        left unset they keep the column default, which is what the ordinary
        add-layers-to-a-project flow wants. ``append_to_layer_order`` puts them at
        the bottom of the project instead of the top.
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

            # Copy properties from the existing project-layer link (preserves user's style)
            # rather than from the base layer (which would reset to default style)
            properties = existing_link.properties if existing_link else layer.properties
            other_properties = existing_link.other_properties if existing_link else layer.other_properties

            # Create layer project link
            layer_project = LayerProjectLink(
                project_id=project_id,
                layer_id=layer.id,
                name=layer_name,
                properties=properties,
                other_properties=other_properties,
                layer_project_group_id=group_id,
                order=(start_order + position) if start_order is not None else 0,
            )

            # Add to database
            layer_project = await CRUDBase(LayerProjectLink).create(
                async_session,
                obj_in=layer_project.model_dump(),
            )
            layer_project_ids.append(layer_project.id)

        # Get project to update layer order
        project = await CRUDBase(Project).get(async_session, id=project_id)
        layer_order = project.layer_order
        # Newly added layers go to the top, unless the caller asked for the bottom.
        if layer_order is None:
            layer_order = layer_project_ids
        elif append_to_layer_order:
            layer_order = layer_order + layer_project_ids
        else:
            layer_order = layer_project_ids + layer_order

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
