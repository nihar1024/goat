import logging
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models._link_model import ResourceGrant
from core.db.models.bundle import Bundle
from core.db.models.folder import Folder
from core.db.models.layer import LayerType
from core.schemas.error import FolderNotFoundError
from core.schemas.folder import FolderCreate, FolderUpdate
from core.services.processes import (
    delete_bundle_artifacts_via_processes,
    delete_layers_via_processes,
)

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

        # Bundles in the folder, read before the cascade removes them. Their
        # member layers are in this folder too, so their DuckLake data is
        # already in the list above — what is not is everything a bundle owns
        # outside Postgres and outside the FK graph.
        bundle_ids = [
            str(bundle_id)
            for bundle_id in (
                await async_session.execute(
                    select(Bundle.id).where(Bundle.folder_id == folder_obj.id)
                )
            )
            .scalars()
            .all()
        ]

        # Remove folder from PostgreSQL (cascades to layer and bundle records)
        await self.remove(async_session, id=folder_obj.id)

        # A bundle's sharing grants live in `resource_grant`, whose `resource_id`
        # is a plain UUID with no foreign key — so they do not cascade with the
        # bundle and would outlive it. Same removal `crud_bundle.delete` does.
        if bundle_ids:
            await async_session.execute(
                sql_delete(ResourceGrant).where(
                    ResourceGrant.resource_type == "bundle",
                    ResourceGrant.resource_id.in_([UUID(b) for b in bundle_ids]),
                )
            )
            await async_session.commit()

        # Delete DuckLake tables via GeoAPI (awaited so job appears immediately)
        if ducklake_layer_ids:
            logger.info(
                "Deleting DuckLake data for %d layers from folder %s via GeoAPI",
                len(ducklake_layer_ids),
                id,
            )
            await delete_layers_via_processes(
                ducklake_layer_ids,
                access_token,
            )

        # Artifact files sit on the data volume, outside both Postgres and
        # DuckLake, so nothing removes them on their own — the same worker
        # cleanup `crud_bundle.delete` dispatches.
        if bundle_ids:
            logger.info(
                "Dispatching artifact cleanup for %d bundle(s) from folder %s",
                len(bundle_ids),
                id,
            )
            await delete_bundle_artifacts_via_processes(bundle_ids, access_token)


folder = CRUDFolder(Folder)
