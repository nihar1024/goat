import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.crud.base import CRUDBase
from core.db.models._link_model import ResourceGrant
from core.db.models.bundle import Bundle
from core.db.models.layer import Layer, LayerType
from core.schemas.bundle import (
    BundleCreate,
    BundleUpdate,
)
from core.services.processes import (
    delete_bundle_artifacts_via_processes,
    delete_layers_via_processes,
)

logger = logging.getLogger(__name__)


class CRUDBundle(CRUDBase[Bundle, BundleCreate, BundleUpdate]):
    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: Bundle,
        obj_in: BundleUpdate | dict[str, Any] | None = None,
    ) -> Bundle:
        """Update a bundle, MERGING `dataset_metadata` rather than replacing it.

        The document holds two authorships at once: what the importer read out
        of the source and what the owner wrote by hand. A caller sends the
        fields it owns, so a plain assignment would let an owner editing the
        licence drop the publisher the import had derived. Merging keeps the
        per-field semantics the eight columns used to have for free.
        """
        if isinstance(obj_in, BundleUpdate):
            data = obj_in.model_dump(exclude_unset=True)
            data.pop("dataset_metadata", None)
            if obj_in.dataset_metadata is not None:
                # `mode="json"` only for the document: it is going into JSONB,
                # where a licence has to be its value and not an enum member.
                # The other fields keep their Python types (`folder_id` is a
                # UUID the model column expects).
                merged = dict(db_obj.dataset_metadata or {})
            # Merge, with null meaning "clear": a key that is absent keeps its
            # stored value, a key sent as null is removed. Without the second
            # rule an emptied field could never be emptied.
            for key, value in obj_in.dataset_metadata.model_dump(
                mode="json", exclude_unset=True
            ).items():
                if value is None:
                    merged.pop(key, None)
                else:
                    merged[key] = value
            data["dataset_metadata"] = merged
            obj_in = data
        return await super().update(db, db_obj=db_obj, obj_in=obj_in)

    async def delete(
        self,
        async_session: AsyncSession,
        *,
        id: UUID,
        user_id: UUID,
        access_token: str,
    ) -> bool:
        """Delete a bundle together with its member layers, cleaning up their
        DuckLake data.

        Membership lives in ``bundle_layer``, so removing the bundle
        only cascades the link rows — the member layers are deleted explicitly
        here (a bundle "stays together"). Their DuckLake tables are dropped via
        GeoAPI and the derived artifacts are removed from the data volume.
        Returns False if no bundle with this id is owned by the user.
        """
        bundles = await self.get_by_multi_keys(
            async_session,
            keys={"id": id, "user_id": user_id},
            extra_fields=[Bundle.layer_links, Bundle.artifacts],
        )
        if len(bundles) == 0:
            return False

        bundle = bundles[0]
        member_layer_ids = [link.layer_id for link in bundle.layer_links]
        has_artifacts = any(a.storage_path for a in bundle.artifacts)

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

        # Delete the bundle (cascades the link/artifact/dependency rows), then
        # the member layer records (cascades their remaining links/share links).
        await async_session.delete(bundle)
        await async_session.flush()
        if member_layer_ids:
            await async_session.execute(
                sql_delete(Layer).where(Layer.id.in_(member_layer_ids))
            )
        # Sharing grants live in resource_grant, which has no FK to the bundle
        # (resource_id is a generic UUID), so they don't cascade — remove them
        # explicitly to avoid orphaned grants.
        await async_session.execute(
            sql_delete(ResourceGrant).where(
                ResourceGrant.resource_type == "bundle",
                ResourceGrant.resource_id == id,
            )
        )
        await async_session.commit()

        if ducklake_layer_ids:
            logger.info(
                "Deleting DuckLake data for %d layers from bundle %s",
                len(ducklake_layer_ids),
                id,
            )
            await delete_layers_via_processes(ducklake_layer_ids, access_token)

        # Artifact files sit on the data volume, so a worker removes them — the
        # same split as the DuckLake/PMTiles cleanup above.
        if has_artifacts:
            logger.info("Dispatching artifact cleanup for bundle %s", id)
            await delete_bundle_artifacts_via_processes([str(id)], access_token)
        return True


bundle = CRUDBundle(Bundle)
