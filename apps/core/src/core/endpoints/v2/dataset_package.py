from typing import List
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from goatlib.models.dataset_package import get_spec
from pydantic import UUID4
from sqlalchemy import and_, or_, select
from sqlalchemy import delete as sql_delete

from core.crud.crud_dataset_package import dataset_package as crud_dataset_package
from core.db.models._link_model import (
    DatasetPackageLayerLink,
    ResourceGrant,
    UserTeamLink,
)
from core.db.models.dataset_package import DatasetPackage
from core.db.models.folder import Folder
from core.db.models.layer import Layer
from core.db.models.organization import Organization
from core.db.models.role import Role
from core.db.models.team import Team
from core.db.models.user import User
from core.db.session import AsyncSession
from core.deps.auth import auth, auth_z
from core.endpoints.deps import get_db, get_user_id
from core.schemas.dataset_package import (
    DatasetPackageCreate,
    DatasetPackageGrantResponse,
    DatasetPackageGrantsResponse,
    DatasetPackageMemberCreate,
    DatasetPackageMemberResponse,
    DatasetPackageRead,
    DatasetPackageShareCreate,
    DatasetPackageUpdate,
    request_examples,
)

RESOURCE_TYPE = "dataset_package"

router = APIRouter()


### Access helpers


async def _user_teams_and_org(
    async_session: AsyncSession, user_id: UUID
) -> tuple[list[UUID], UUID | None]:
    team_ids = list(
        (
            await async_session.execute(
                select(UserTeamLink.team_id).where(UserTeamLink.user_id == user_id)
            )
        ).scalars()
    )
    org_id = (
        await async_session.execute(
            select(User.organization_id).where(User.id == user_id)
        )
    ).scalar_one_or_none()
    return team_ids, org_id


def _grant_conditions(team_ids: list[UUID], org_id: UUID | None) -> list:
    """resource_grant match conditions for the caller's teams / organization."""
    conds = []
    if team_ids:
        conds.append(
            and_(
                ResourceGrant.grantee_type == "team",
                ResourceGrant.grantee_id.in_(team_ids),
            )
        )
    if org_id is not None:
        conds.append(
            and_(
                ResourceGrant.grantee_type == "organization",
                ResourceGrant.grantee_id == org_id,
            )
        )
    return conds


async def _owned_package_or_404(
    async_session: AsyncSession, dataset_package_id: UUID, user_id: UUID
) -> DatasetPackage:
    """Owner-only access — for management operations (update/delete/share/members)."""
    package = await async_session.get(DatasetPackage, dataset_package_id)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset package not found"
        )
    if package.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the dataset package owner can perform this action",
        )
    return package


async def _accessible_package_or_404(
    async_session: AsyncSession, dataset_package_id: UUID, user_id: UUID
) -> DatasetPackage:
    """Read access — the owner, or anyone the package is shared with via a
    dataset_package resource grant to their team/organization."""
    package = await async_session.get(DatasetPackage, dataset_package_id)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset package not found"
        )
    if package.user_id == user_id:
        return package
    team_ids, org_id = await _user_teams_and_org(async_session, user_id)
    conds = _grant_conditions(team_ids, org_id)
    if conds:
        granted = (
            await async_session.execute(
                select(ResourceGrant.id)
                .where(
                    ResourceGrant.resource_type == RESOURCE_TYPE,
                    ResourceGrant.resource_id == dataset_package_id,
                    or_(*conds),
                )
                .limit(1)
            )
        ).first()
        if granted is not None:
            return package
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Dataset package not found"
    )


### Dataset package CRUD endpoints


@router.post(
    "",
    summary="Create a new dataset package",
    response_model=DatasetPackageRead,
    status_code=201,
    dependencies=[Depends(auth_z)],
)
async def create_dataset_package(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    package_in: DatasetPackageCreate = Body(..., example=request_examples["create"]),
) -> DatasetPackageRead:
    """Create a new dataset package in a folder the caller owns."""
    folder = await async_session.get(Folder, package_in.folder_id)
    if folder is None or folder.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found"
        )
    package_in.user_id = user_id
    created = await crud_dataset_package.create(async_session, obj_in=package_in)
    return DatasetPackageRead(**created.model_dump())


@router.get(
    "",
    summary="List the caller's dataset packages",
    response_model=List[DatasetPackageRead],
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def list_dataset_packages(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
) -> List[DatasetPackageRead]:
    """List dataset packages the caller owns or has been shared."""
    team_ids, org_id = await _user_teams_and_org(async_session, user_id)
    conds = _grant_conditions(team_ids, org_id)
    stmt = select(DatasetPackage)
    if conds:
        shared_ids = select(ResourceGrant.resource_id).where(
            ResourceGrant.resource_type == RESOURCE_TYPE, or_(*conds)
        )
        stmt = stmt.where(
            or_(DatasetPackage.user_id == user_id, DatasetPackage.id.in_(shared_ids))
        )
    else:
        stmt = stmt.where(DatasetPackage.user_id == user_id)
    result = await async_session.execute(stmt)
    return [DatasetPackageRead(**p.model_dump()) for p in result.scalars().all()]


@router.get(
    "/{dataset_package_id}",
    summary="Retrieve a dataset package by its ID",
    response_model=DatasetPackageRead,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def read_dataset_package(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package ID"),
) -> DatasetPackageRead:
    """Retrieve a dataset package the caller owns or has been shared."""
    package = await _accessible_package_or_404(
        async_session, dataset_package_id, user_id
    )
    return DatasetPackageRead(**package.model_dump())


@router.put(
    "/{dataset_package_id}",
    summary="Update a dataset package",
    response_model=DatasetPackageRead,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def update_dataset_package(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package ID"),
    package_in: DatasetPackageUpdate = Body(...),
) -> DatasetPackageRead:
    """Update a dataset package owned by the caller."""
    packages = await crud_dataset_package.get_by_multi_keys(
        async_session, keys={"id": dataset_package_id, "user_id": user_id}
    )
    if len(packages) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset package not found"
        )
    updated = await crud_dataset_package.update(
        async_session, db_obj=packages[0], obj_in=package_in
    )
    return DatasetPackageRead(**updated.model_dump())


@router.delete(
    "/{dataset_package_id}",
    summary="Delete a dataset package and all its member layers",
    status_code=204,
    dependencies=[Depends(auth_z)],
)
async def delete_dataset_package(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    access_token: str = Depends(auth),
    dataset_package_id: UUID4 = Path(..., description="The dataset package ID"),
) -> None:
    """Delete a dataset package. Member layers are removed via cascade, and their
    DuckLake data is cleaned up via GeoAPI."""
    deleted = await crud_dataset_package.delete(
        async_session,
        id=dataset_package_id,
        user_id=user_id,
        access_token=access_token,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset package not found"
        )
    return


### Dataset package membership endpoints
#
# Membership lives in the dataset_package_layer link table: a layer belongs to
# at most one package, tagged with the role it plays (a spec role key from
# goatlib). Roles are validated against the package type's spec.


@router.get(
    "/{dataset_package_id}/layers",
    summary="List the layers in a dataset package with their roles",
    response_model=List[DatasetPackageMemberResponse],
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def list_dataset_package_layers(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package"),
) -> List[DatasetPackageMemberResponse]:
    """List member layers and their roles (owner or shared)."""
    await _accessible_package_or_404(async_session, dataset_package_id, user_id)
    links = (
        await async_session.execute(
            select(DatasetPackageLayerLink).where(
                DatasetPackageLayerLink.dataset_package_id == dataset_package_id
            )
        )
    ).scalars()
    return [
        DatasetPackageMemberResponse(layer_id=link.layer_id, role=link.role)
        for link in links
    ]


@router.post(
    "/{dataset_package_id}/layers",
    summary="Add a layer to a dataset package (or re-tag its role)",
    response_model=DatasetPackageMemberResponse,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def add_dataset_package_layer(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package"),
    payload: DatasetPackageMemberCreate = Body(...),
) -> DatasetPackageMemberResponse:
    """Add a layer to the package with a role, or update the role if the layer
    is already a member. Owner only."""
    package = await _owned_package_or_404(async_session, dataset_package_id, user_id)

    # Role must be a valid role key for this package type's spec.
    if payload.role is not None:
        spec = get_spec(package.dataset_package_type)
        if payload.role not in spec.role_keys():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid role '{payload.role}' for dataset package type "
                    f"'{spec.type.value}'. "
                    f"Allowed roles: {list(spec.role_keys())}"
                ),
            )

    # The layer must be owned by the caller.
    layer = await async_session.get(Layer, payload.layer_id)
    if layer is None or layer.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Layer not found"
        )

    existing = (
        await async_session.execute(
            select(DatasetPackageLayerLink).where(
                DatasetPackageLayerLink.layer_id == payload.layer_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.dataset_package_id != dataset_package_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Layer already belongs to another dataset package",
        )

    # A role can be filled by only one layer within the package.
    if payload.role is not None:
        role_taken = (
            await async_session.execute(
                select(DatasetPackageLayerLink.id).where(
                    DatasetPackageLayerLink.dataset_package_id == dataset_package_id,
                    DatasetPackageLayerLink.role == payload.role,
                    DatasetPackageLayerLink.layer_id != payload.layer_id,
                )
            )
        ).first()
        if role_taken is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Role '{payload.role}' is already assigned in this package",
            )

    if existing is not None:
        existing.role = payload.role
        link = existing
    else:
        link = DatasetPackageLayerLink(
            dataset_package_id=dataset_package_id,
            layer_id=payload.layer_id,
            role=payload.role,
        )
        async_session.add(link)
    await async_session.commit()
    return DatasetPackageMemberResponse(layer_id=link.layer_id, role=link.role)


@router.delete(
    "/{dataset_package_id}/layers/{layer_id}",
    summary="Remove a layer from a dataset package",
    status_code=204,
    dependencies=[Depends(auth_z)],
)
async def remove_dataset_package_layer(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package"),
    layer_id: UUID4 = Path(..., description="The member layer to remove"),
) -> None:
    """Remove a layer from the package (the layer itself is not deleted; it
    becomes a standalone layer again). Owner only."""
    await _owned_package_or_404(async_session, dataset_package_id, user_id)
    result = await async_session.execute(
        sql_delete(DatasetPackageLayerLink).where(
            and_(
                DatasetPackageLayerLink.dataset_package_id == dataset_package_id,
                DatasetPackageLayerLink.layer_id == layer_id,
            )
        )
    )
    await async_session.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layer is not a member of this package",
        )


### Dataset package sharing endpoints
#
# A dataset package is the sole sharing unit for its member layers: sharing a
# package with a team/organisation grants access to every member layer (derived
# at authorization time in check_layer.sql). Member layers cannot be shared
# individually (enforced in the layer share endpoint).


@router.post(
    "/{dataset_package_id}/share",
    summary="Share a dataset package with a team or organization",
    response_model=DatasetPackageGrantsResponse,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def share_dataset_package(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package to share"),
    payload: DatasetPackageShareCreate = Body(...),
) -> DatasetPackageGrantsResponse:
    """Share a dataset package with a team or organization. Owner only."""
    await _owned_package_or_404(async_session, dataset_package_id, user_id)

    role = (
        await async_session.execute(select(Role).where(Role.name == payload.role))
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role: {payload.role}",
        )

    # Upsert: replace any existing grant for this grantee.
    await async_session.execute(
        sql_delete(ResourceGrant).where(
            and_(
                ResourceGrant.resource_type == RESOURCE_TYPE,
                ResourceGrant.resource_id == dataset_package_id,
                ResourceGrant.grantee_type == payload.grantee_type,
                ResourceGrant.grantee_id == payload.grantee_id,
            )
        )
    )
    async_session.add(
        ResourceGrant(
            resource_type=RESOURCE_TYPE,
            resource_id=dataset_package_id,
            grantee_type=payload.grantee_type,
            grantee_id=payload.grantee_id,
            role_id=role.id,
            granted_by=user_id,
        )
    )
    await async_session.commit()
    return await _get_grants_response(async_session, dataset_package_id)


@router.get(
    "/{dataset_package_id}/share",
    summary="List current grants for a dataset package",
    response_model=DatasetPackageGrantsResponse,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def get_dataset_package_grants(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package"),
) -> DatasetPackageGrantsResponse:
    """List the grants on a dataset package. Owner only."""
    await _owned_package_or_404(async_session, dataset_package_id, user_id)
    return await _get_grants_response(async_session, dataset_package_id)


@router.delete(
    "/{dataset_package_id}/share/{grantee_type}/{grantee_id}",
    summary="Remove a grant from a dataset package",
    status_code=204,
    dependencies=[Depends(auth_z)],
)
async def delete_dataset_package_grant(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package"),
    grantee_type: str = Path(..., description="team or organization"),
    grantee_id: UUID4 = Path(..., description="The team or organization ID"),
) -> None:
    """Remove a specific grant from a dataset package. Owner only."""
    await _owned_package_or_404(async_session, dataset_package_id, user_id)
    result = await async_session.execute(
        sql_delete(ResourceGrant).where(
            and_(
                ResourceGrant.resource_type == RESOURCE_TYPE,
                ResourceGrant.resource_id == dataset_package_id,
                ResourceGrant.grantee_type == grantee_type,
                ResourceGrant.grantee_id == grantee_id,
            )
        )
    )
    await async_session.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found"
        )


### Helpers


async def _get_grants_response(
    async_session: AsyncSession, dataset_package_id: UUID
) -> DatasetPackageGrantsResponse:
    """Fetch all grants for a package, enriched with grantee display names."""
    rows = (
        await async_session.execute(
            select(ResourceGrant, Role)
            .join(Role, Role.id == ResourceGrant.role_id)
            .where(
                ResourceGrant.resource_type == RESOURCE_TYPE,
                ResourceGrant.resource_id == dataset_package_id,
            )
        )
    ).all()

    enriched: list[DatasetPackageGrantResponse] = []
    for grant, role in rows:
        name = str(grant.grantee_id)
        if grant.grantee_type == "team":
            team = await async_session.get(Team, grant.grantee_id)
            if team:
                name = team.name
        elif grant.grantee_type == "organization":
            org = await async_session.get(Organization, grant.grantee_id)
            if org:
                name = org.name
        enriched.append(
            DatasetPackageGrantResponse(
                grantee_type=grant.grantee_type,
                grantee_id=grant.grantee_id,
                grantee_name=name,
                role=role.name,
            )
        )
    return DatasetPackageGrantsResponse(grants=enriched)
