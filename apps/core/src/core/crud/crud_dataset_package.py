import logging
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.core.config import settings
from core.crud.base import CRUDBase
from core.db.models.dataset_package import DatasetPackage
from core.db.models.layer import Layer, LayerType
from core.schemas.dataset_package import (
    DatasetPackageCreate,
    DatasetPackageUpdate,
)
from core.services.geoapi import delete_layers_via_geoapi
from core.services.s3 import s3_service

logger = logging.getLogger(__name__)


class CRUDDatasetPackage(
    CRUDBase[DatasetPackage, DatasetPackageCreate, DatasetPackageUpdate]
):
    async def delete(
        self,
        async_session: AsyncSession,
        *,
        id: UUID,
        user_id: UUID,
        access_token: str,
    ) -> bool:
        """Delete a package together with its member layers, cleaning up their
        DuckLake data.

        Membership lives in ``dataset_package_layer``, so removing the package
        only cascades the link rows — the member layers are deleted explicitly
        here (a package "stays together"). Their DuckLake tables are dropped via
        GeoAPI and the derived artifacts' object-storage blobs are removed too.
        Returns False if no package with this id is owned by the user.
        """
        packages = await self.get_by_multi_keys(
            async_session,
            keys={"id": id, "user_id": user_id},
            extra_fields=[DatasetPackage.layer_links, DatasetPackage.artifacts],
        )
        if len(packages) == 0:
            return False

        package = packages[0]
        member_layer_ids = [link.layer_id for link in package.layer_links]
        # Artifact blobs live in object storage; the rows cascade with the
        # package but the S3 objects must be removed explicitly.
        artifact_s3_keys = [a.s3_key for a in package.artifacts if a.s3_key]

        # Only feature/table layers have DuckLake tables — resolve types by id
        # without pulling full ORM objects into the session.
        ducklake_layer_ids: list[str] = []
        if member_layer_ids:
            rows = (
                await async_session.execute(
                    select(Layer.id, Layer.type).where(Layer.id.in_(member_layer_ids))
                )
            ).all()
            ducklake_layer_ids = [
                str(lid)
                for lid, ltype in rows
                if ltype in (LayerType.feature, LayerType.table)
            ]

        # Delete the package (cascades the link rows via delete-orphan), then the
        # member layer records (cascades their remaining links/share links).
        await async_session.delete(package)
        await async_session.flush()
        if member_layer_ids:
            await async_session.execute(
                sql_delete(Layer).where(Layer.id.in_(member_layer_ids))
            )
        await async_session.commit()

        if ducklake_layer_ids:
            logger.info(
                "Deleting DuckLake data for %d layers from dataset package %s",
                len(ducklake_layer_ids),
                id,
            )
            await delete_layers_via_geoapi(
                ducklake_layer_ids, str(user_id), access_token
            )

        # Best-effort artifact blob cleanup — a failure here must not undo the
        # (already committed) DB deletion.
        for key in artifact_s3_keys:
            try:
                s3_service.delete_file(settings.S3_BUCKET_NAME, key)
            except Exception as e:
                logger.warning(
                    "Failed to delete artifact blob %s for dataset package %s: %s",
                    key,
                    id,
                    e,
                )
        return True


dataset_package = CRUDDatasetPackage(DatasetPackage)
