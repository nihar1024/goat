import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models.folder import Folder
from core.db.models.layer import LayerType
from core.schemas.error import FolderNotFoundError
from core.schemas.folder import FolderCreate, FolderUpdate
from core.services.geoapi import delete_layers_via_geoapi

from .base import CRUDBase

logger = logging.getLogger(__name__)


class CRUDFolder(CRUDBase[Folder, FolderCreate, FolderUpdate]):
    async def delete(
        self,
        async_session: AsyncSession,
        *,
        id: UUID,
        user_id: UUID,
        access_token: str,
    ) -> None:
        db_obj = await self.get_by_multi_keys(
            async_session,
            keys={"id": id, "user_id": user_id},
            extra_fields=[Folder.layers],
        )
        # Check if folder exists
        if len(db_obj) == 0:
            raise FolderNotFoundError("Folder not found")

        folder_obj = db_obj[0]

        # Collect layer IDs that have DuckLake tables (feature and table layers)
        ducklake_layer_ids: list[str] = []
        if folder_obj.layers:
            for layer in folder_obj.layers:
                # Only feature and table layers have DuckLake tables
                if layer.type in [LayerType.feature, LayerType.table]:
                    ducklake_layer_ids.append(str(layer.id))

        # Remove folder from PostgreSQL (cascades to layer records)
        await self.remove(async_session, id=folder_obj.id)

        # Delete DuckLake tables via GeoAPI (awaited so job appears immediately)
        if ducklake_layer_ids:
            logger.info(
                "Deleting DuckLake data for %d layers from folder %s via GeoAPI",
                len(ducklake_layer_ids),
                id,
            )
            await delete_layers_via_geoapi(
                ducklake_layer_ids,
                str(user_id),
                access_token,
            )


folder = CRUDFolder(Folder)
