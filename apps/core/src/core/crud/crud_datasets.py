# Standard library imports
from typing import Any
from uuid import UUID

# Third party imports
from fastapi_pagination import Page
from fastapi_pagination import Params as PaginationParams
from fastapi_pagination.ext.sqlalchemy import paginate
from pydantic import BaseModel
from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application imports
from core.core.content import build_shared_with_object, create_query_shared_content
from core.crud.base import CRUDBase
from core.crud.crud_layer import layer as crud_layer
from core.db.models._link_model import (
    LayerOrganizationLink,
    LayerTeamLink,
    ResourceGrant,
)
from core.db.models.dataset_package import DatasetPackage
from core.db.models.folder import Folder
from core.db.models.layer import Layer
from core.db.models.organization import Organization
from core.db.models.role import Role
from core.db.models.team import Team
from core.db.models.user import User
from core.schemas.dataset_package import DatasetContentTile
from core.schemas.layer import ILayerGet


class CRUDDatasets:
    """Listing across the two dataset content types — layers and dataset
    packages — unified into a single paginated, sorted ``DatasetContentTile``
    result.

    Layer filtering/hydration is delegated to ``CRUDLayer`` (``get_base_filter``
    and the shared-content query helpers); this class owns the union, pagination,
    the package side, and the tile projection.
    """

    # Filters only a layer can satisfy — when any is set, dataset packages are
    # excluded from the mixed listing (a package is not a feature layer, has no
    # geometry, etc.), so the result stays consistent with the filter.
    _DATASET_PACKAGE_INCOMPATIBLE_FILTERS = (
        "type",
        "feature_layer_type",
        "license",
        "data_category",
        "geographical_code",
        "language_code",
        "distributor_name",
        "spatial_search",
        "in_catalog",
    )

    @staticmethod
    def _grant_match(team_id: UUID | None, organization_id: UUID | None) -> list[Any]:
        """ResourceGrant grantee conditions for the active team/org."""
        conds: list[Any] = []
        if team_id:
            conds.append(
                and_(
                    ResourceGrant.grantee_type == "team",
                    ResourceGrant.grantee_id == team_id,
                )
            )
        if organization_id:
            conds.append(
                and_(
                    ResourceGrant.grantee_type == "organization",
                    ResourceGrant.grantee_id == organization_id,
                )
            )
        return conds

    def _layer_access_filters(
        self,
        folder_id: UUID | None,
        team_id: UUID | None,
        organization_id: UUID | None,
        granted_folder_ids: Any,
        folder_granted: bool,
    ) -> list[Any]:
        """Layer access conditions (WHERE) in a team/org context — mirrors
        ``get_layers_with_filter``. Empty in personal context, where
        ``get_base_filter`` already scopes to the owner."""
        if not team_id and not organization_id:
            return []
        direct: list[Any] = []
        if team_id:
            direct.append(
                Layer.id.in_(
                    select(LayerTeamLink.layer_id).where(LayerTeamLink.team_id == team_id)
                )
            )
        if organization_id:
            direct.append(
                Layer.id.in_(
                    select(LayerOrganizationLink.layer_id).where(
                        LayerOrganizationLink.organization_id == organization_id
                    )
                )
            )
        direct_link = or_(*direct)
        if folder_id is not None:
            # Granted folder → all its layers (folder_id already filtered by
            # get_base_filter); otherwise only directly-linked layers in it.
            return [] if folder_granted else [direct_link]
        # Root: directly-linked layers, excluding those inside a granted folder
        # (those surface only when navigating into that folder).
        return [
            and_(
                direct_link,
                or_(
                    Layer.folder_id.is_(None),
                    Layer.folder_id.notin_(granted_folder_ids),
                ),
            )
        ]

    def _dataset_package_access_filters(
        self,
        user_id: UUID,
        folder_id: UUID | None,
        team_id: UUID | None,
        organization_id: UUID | None,
        granted_folder_ids: Any,
        folder_granted: bool,
    ) -> list[Any]:
        """Dataset-package access conditions (WHERE). Personal: owned + folder
        scope. Team/org: packages shared directly via a grant OR living in a
        folder shared with the team/org — so packages inherit folder grants the
        same way layers do, keeping the folder hierarchy intact."""
        if not team_id and not organization_id:
            filters: list[Any] = [DatasetPackage.user_id == user_id]
            if folder_id is not None:
                filters.append(DatasetPackage.folder_id == folder_id)
            else:
                filters.append(
                    or_(
                        DatasetPackage.folder_id.is_(None),
                        DatasetPackage.folder_id.in_(
                            select(Folder.id).where(Folder.user_id == user_id)
                        ),
                    )
                )
            return filters
        grant_conds = self._grant_match(team_id, organization_id)
        granted_dataset_package_ids = select(ResourceGrant.resource_id).where(
            ResourceGrant.resource_type == "dataset_package", or_(*grant_conds)
        )
        direct_dataset_package = DatasetPackage.id.in_(granted_dataset_package_ids)
        if folder_id is not None:
            # Granted folder → every package in it; otherwise only directly-
            # granted packages in the folder.
            return (
                [DatasetPackage.folder_id == folder_id]
                if folder_granted
                else [DatasetPackage.folder_id == folder_id, direct_dataset_package]
            )
        # Root: directly-granted packages not inside a granted folder (those
        # surface when navigating into that folder, mirroring layers).
        return [
            and_(
                direct_dataset_package,
                or_(
                    DatasetPackage.folder_id.is_(None),
                    DatasetPackage.folder_id.notin_(granted_folder_ids),
                ),
            )
        ]

    async def list_content(
        self,
        async_session: AsyncSession,
        user_id: UUID,
        order_by: str,
        order: str,
        page_params: PaginationParams,
        params: ILayerGet | None,
        team_id: UUID | None = None,
        organization_id: UUID | None = None,
    ) -> Page[BaseModel]:
        """List layers and dataset packages together as one paginated, sorted
        result.

        A ``UNION ALL`` of lightweight ``(id, kind, name, created_at,
        updated_at)`` rows from both sources is ordered and paginated by the
        database, then each page item is hydrated to its full tile shape — so
        packages are integrated by the sort key rather than bolted on. Works in
        personal, folder, and team/organization contexts (access is expressed
        entirely as WHERE conditions for both sources).
        """
        if params is None:
            params = ILayerGet()
        folder_id = getattr(params, "folder_id", None)

        # Team/org shared-access context, computed once and shared by the layer
        # and package access filters (folders granted to the caller's team/org,
        # and whether the folder being browsed is one of them).
        grant_conds = (
            self._grant_match(team_id, organization_id)
            if (team_id or organization_id)
            else []
        )
        granted_folder_ids = (
            select(ResourceGrant.resource_id).where(
                ResourceGrant.resource_type == "folder", or_(*grant_conds)
            )
            if grant_conds
            else None
        )
        folder_granted = False
        if folder_id is not None and grant_conds:
            folder_granted = (
                await async_session.execute(
                    select(ResourceGrant.id)
                    .where(
                        ResourceGrant.resource_type == "folder",
                        ResourceGrant.resource_id == folder_id,
                        or_(*grant_conds),
                    )
                    .limit(1)
                )
            ).first() is not None

        # Layer access filters (WHERE-based). get_base_filter covers "My Content";
        # in a team/org context it only adds non-access filters, so add the
        # shared-access conditions here (mirrors get_layers_with_filter).
        layer_filters = await crud_layer.get_base_filter(
            user_id=user_id,
            params=params,
            team_id=team_id,
            organization_id=organization_id,
        )
        layer_filters += self._layer_access_filters(
            folder_id=folder_id,
            team_id=team_id,
            organization_id=organization_id,
            granted_folder_ids=granted_folder_ids,
            folder_granted=folder_granted,
        )
        layer_rows = select(
            Layer.id.label("id"),
            literal("layer").label("kind"),
            Layer.name.label("name"),
            Layer.created_at.label("created_at"),
            Layer.updated_at.label("updated_at"),
        ).where(and_(*layer_filters))

        include_dataset_packages = not any(
            getattr(params, f, None) is not None
            for f in self._DATASET_PACKAGE_INCOMPATIBLE_FILTERS
        )
        if include_dataset_packages:
            dataset_package_filters = self._dataset_package_access_filters(
                user_id=user_id,
                folder_id=folder_id,
                team_id=team_id,
                organization_id=organization_id,
                granted_folder_ids=granted_folder_ids,
                folder_granted=folder_granted,
            )
            if params.search is not None:
                dataset_package_filters.append(
                    func.lower(DatasetPackage.name).contains(params.search.lower())
                )
            dataset_package_rows = select(
                DatasetPackage.id.label("id"),
                literal("dataset_package").label("kind"),
                DatasetPackage.name.label("name"),
                DatasetPackage.created_at.label("created_at"),
                DatasetPackage.updated_at.label("updated_at"),
            ).where(and_(*dataset_package_filters))
            union_sq = layer_rows.union_all(dataset_package_rows).subquery()
        else:
            union_sq = layer_rows.subquery()

        sort_key = order_by if order_by in ("name", "created_at", "updated_at") else "updated_at"
        sort_col = union_sq.c[sort_key]
        # ``order`` may arrive as an OrderEnum; compare on its value.
        is_ascending = str(getattr(order, "value", order)) == "ascendent"
        ordered = select(union_sq).order_by(
            sort_col.asc() if is_ascending else sort_col.desc()
        )

        page = await paginate(async_session, ordered, page_params)
        assert isinstance(page, Page)
        rows = page.items
        layer_ids = [r.id for r in rows if r.kind == "layer"]
        dataset_package_ids = [r.id for r in rows if r.kind == "dataset_package"]

        def enum_value(value: Any) -> Any:
            return getattr(value, "value", value)

        def scope_shared_with(shared_with: Any) -> Any:
            """In a team/org view, keep only the active grantee so the tile's
            role chip resolves to the current team/org (layers are hydrated with
            all their links)."""
            if not shared_with or (not team_id and not organization_id):
                return shared_with
            if team_id:
                return {
                    "teams": [
                        t
                        for t in shared_with.get("teams", [])
                        if str(t.get("id")) == str(team_id)
                    ],
                    "organizations": [],
                }
            return {
                "teams": [],
                "organizations": [
                    o
                    for o in shared_with.get("organizations", [])
                    if str(o.get("id")) == str(organization_id)
                ],
            }

        # Hydrate layers as content tiles (reusing the standard owned_by/
        # shared_with machinery), so a layer and a package share one shape.
        tile_by_id: dict[str, DatasetContentTile] = {}
        if layer_ids:
            roles = await CRUDBase(Role).get_all(async_session)
            role_mapping = {role.id: role.name for role in roles}
            query = create_query_shared_content(
                Layer,
                LayerTeamLink,
                LayerOrganizationLink,
                Team,
                Organization,
                Role,
                [Layer.id.in_(layer_ids)],
            )
            result = await async_session.execute(query)
            for d in build_shared_with_object(
                items=result.all(),
                role_mapping=role_mapping,
                team_key="team_links",
                org_key="organization_links",
                model_name="layer",
            ):
                tile_by_id[str(d["id"])] = DatasetContentTile(
                    content_type="layer",
                    id=d["id"],
                    name=d.get("name"),
                    folder_id=d.get("folder_id"),
                    type=enum_value(d.get("type")),
                    data_type=enum_value(d.get("data_type")),
                    thumbnail_url=d.get("thumbnail_url"),
                    owned_by=d.get("owned_by"),
                    shared_with=scope_shared_with(d.get("shared_with")),
                    tags=d.get("tags"),
                    created_at=d.get("created_at"),
                    updated_at=d.get("updated_at"),
                )

        # Hydrate packages into the same content-tile shape.
        if dataset_package_ids:
            prows = (
                await async_session.execute(
                    select(
                        DatasetPackage,
                        User.id,
                        User.firstname,
                        User.lastname,
                        User.avatar,
                    )
                    .join(User, User.id == DatasetPackage.user_id)
                    .where(DatasetPackage.id.in_(dataset_package_ids))
                )
            ).all()
            for dataset_package, uid, firstname, lastname, avatar in prows:
                dataset_package_type = enum_value(dataset_package.dataset_package_type)
                tile_by_id[str(dataset_package.id)] = DatasetContentTile(
                    content_type="dataset_package",
                    id=dataset_package.id,
                    name=dataset_package.name,
                    folder_id=dataset_package.folder_id,
                    type=dataset_package_type,
                    dataset_package_type=dataset_package_type,
                    status=enum_value(dataset_package.status),
                    description=dataset_package.description,
                    owned_by={
                        "id": uid,
                        "firstname": firstname,
                        "lastname": lastname,
                        "avatar": avatar,
                    },
                    created_at=dataset_package.created_at,
                    updated_at=dataset_package.updated_at,
                )

        # Reassemble in the DB's paginated order.
        page.items = [tile_by_id[str(r.id)] for r in rows if str(r.id) in tile_by_id]
        return page


datasets = CRUDDatasets()
