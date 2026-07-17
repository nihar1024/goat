import os
import tempfile
from typing import List, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from goatlib.dataset_packages.importers import get_importer
from goatlib.models.dataset_package import (
    DatasetPackageStatus,
    DatasetPackageTypeName,
    get_spec,
)
from pydantic import UUID4
from sqlalchemy import and_, or_, select
from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update

from core.core.config import settings
from core.crud.crud_dataset_package import dataset_package as crud_dataset_package
from core.db.models._link_model import (
    DatasetPackageDependencyLink,
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
    DatasetPackageDependencyCreate,
    DatasetPackageDependencyResponse,
    DatasetPackageGrantResponse,
    DatasetPackageGrantsResponse,
    DatasetPackageImportRequest,
    DatasetPackageImportResponse,
    DatasetPackageMemberCreate,
    DatasetPackageMemberResponse,
    DatasetPackageRead,
    DatasetPackageShareCreate,
    DatasetPackageUpdate,
    request_examples,
)
from core.services.geoapi import execute_process
from core.services.s3 import s3_service

RESOURCE_TYPE = "dataset_package"

router = APIRouter()


def infer_dataset_package_type(filename: str) -> "DatasetPackageTypeName | None":
    """Map an uploaded file name to a dataset package type. For now: any file
    named ``*gtfs*.zip`` (case-insensitive) is a GTFS PT network."""
    lower = filename.lower()
    if lower.endswith(".zip") and "gtfs" in lower:
        return DatasetPackageTypeName.pt_network_gtfs
    return None


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


# Grant roles that confer each access level on a package. Access is grant-based
# (like folders): a package's own grant, or a grant on the folder it lives in
# (folder grants cascade to the package), plus ownership.
_DATASET_PACKAGE_EDITOR_ROLES = {"dataset-package-editor", "folder-editor"}
_DATASET_PACKAGE_VIEWER_ROLES = _DATASET_PACKAGE_EDITOR_ROLES | {
    "dataset-package-viewer",
    "folder-viewer",
}

DatasetPackageAccess = Literal["read", "write", "owner"]


async def authorize_dataset_package(
    async_session: AsyncSession,
    dataset_package_id: UUID,
    user_id: UUID,
    level: DatasetPackageAccess,
) -> DatasetPackage:
    """Single authorization gate for a dataset package.

    Resolves the caller's effective access from ownership, the package's own
    grants, and its folder's grants (folder grants cascade to the package), then
    checks it against the required level:

    * ``read``  — viewer or above (view/list),
    * ``write`` — editor or above (update, move, members, dependencies, share),
    * ``owner`` — the package owner only (delete — a whole-package cascade).

    Returns the package, or raises 404 (no access — existence not leaked) /
    403 (has read access but not the required level).
    """
    dataset_package = await async_session.get(DatasetPackage, dataset_package_id)
    if dataset_package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset package not found"
        )
    if dataset_package.user_id == user_id:
        return dataset_package
    if level == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the dataset package owner can perform this action",
        )

    team_ids, org_id = await _user_teams_and_org(async_session, user_id)
    conds = _grant_conditions(team_ids, org_id)
    role_names: set[str] = set()
    if conds:
        role_names = set(
            (
                await async_session.execute(
                    select(Role.name)
                    .join(ResourceGrant, ResourceGrant.role_id == Role.id)
                    .where(
                        or_(
                            and_(
                                ResourceGrant.resource_type == RESOURCE_TYPE,
                                ResourceGrant.resource_id == dataset_package_id,
                            ),
                            and_(
                                ResourceGrant.resource_type == "folder",
                                ResourceGrant.resource_id == dataset_package.folder_id,
                            ),
                        ),
                        or_(*conds),
                    )
                )
            )
            .scalars()
            .all()
        )
    is_editor = bool(role_names & _DATASET_PACKAGE_EDITOR_ROLES)
    is_viewer = is_editor or bool(role_names & _DATASET_PACKAGE_VIEWER_ROLES)
    if level == "write" and is_editor:
        return dataset_package
    if level == "read" and is_viewer:
        return dataset_package
    if is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have edit access to this dataset package",
        )
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


@router.post(
    "/import",
    summary="Import an uploaded file (e.g. gtfs.zip) as a dataset package",
    response_model=DatasetPackageImportResponse,
    status_code=202,
    dependencies=[Depends(auth_z)],
)
async def import_dataset_package(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    access_token: str = Depends(auth),
    payload: DatasetPackageImportRequest = Body(...),
) -> DatasetPackageImportResponse:
    """Route an uploaded file to the right dataset-package importer by filename
    (``*gtfs*.zip`` → GTFS PT network), validate it synchronously against the
    type's spec, create the package (status=processing) and optional street
    dependency, then ingest the member layers in the background."""
    filename = payload.s3_key.rsplit("/", 1)[-1]
    dataset_package_type = infer_dataset_package_type(filename)
    if dataset_package_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{filename}' is not a recognised dataset package upload "
                "(expected e.g. a *gtfs*.zip)"
            ),
        )

    folder = await async_session.get(Folder, payload.folder_id)
    if folder is None or folder.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found"
        )

    # Synchronous validation: download and check the source against the spec.
    tmp_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
    try:
        s3_service.download_file(settings.S3_BUCKET_NAME, payload.s3_key, tmp_path)
        validation = get_importer(dataset_package_type).validate(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"Invalid {dataset_package_type.value} upload",
                "errors": validation.errors,
                "missing_required_roles": validation.missing_required_roles,
            },
        )

    # Validate the optional street-network dependency before creating anything.
    link_street = False
    if payload.street_network_package_id is not None:
        dep_spec = get_spec(dataset_package_type).dependency("street_network")
        if dep_spec is not None:
            target = await authorize_dataset_package(
                async_session, payload.street_network_package_id, user_id, "read"
            )
            if str(target.dataset_package_type) != dep_spec.package_type.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "street_network_package_id must reference a "
                        f"'{dep_spec.package_type.value}' package"
                    ),
                )
            link_street = True

    # Create the package shell (processing) + optional dependency, synchronously.
    dataset_package = DatasetPackage(
        user_id=user_id,
        folder_id=payload.folder_id,
        name=payload.name,
        description=payload.description,
        dataset_package_type=dataset_package_type,
        status=DatasetPackageStatus.processing,
    )
    async_session.add(dataset_package)
    await async_session.flush()
    if link_street:
        async_session.add(
            DatasetPackageDependencyLink(
                dataset_package_id=dataset_package.id,
                depends_on_package_id=payload.street_network_package_id,
                dependency_kind="street_network",
            )
        )
    await async_session.commit()
    await async_session.refresh(dataset_package)

    # Trigger the ingest as a Windmill job via the processes service. The job
    # ingests the member layers and flips the package status to ready/failed.
    try:
        job_id = await execute_process(
            process_id="dataset_package_import",
            inputs={
                "package_id": str(dataset_package.id),
                "s3_key": payload.s3_key,
                "dataset_package_type": dataset_package_type.value,
                "folder_id": str(payload.folder_id),
            },
            access_token=access_token,
        )
    except Exception:
        # The shell is committed; mark it failed so it isn't stuck "processing".
        dataset_package.status = DatasetPackageStatus.failed
        await async_session.commit()
        raise

    return DatasetPackageImportResponse(
        package=DatasetPackageRead(**dataset_package.model_dump()), job_id=job_id
    )


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
    # Join the owner so tiles can show an avatar (same "owned_by" shape as layers).
    stmt = select(
        DatasetPackage,
        User.id,
        User.firstname,
        User.lastname,
        User.avatar,
    ).join(User, User.id == DatasetPackage.user_id)
    if conds:
        shared_ids = select(ResourceGrant.resource_id).where(
            ResourceGrant.resource_type == RESOURCE_TYPE, or_(*conds)
        )
        stmt = stmt.where(
            or_(DatasetPackage.user_id == user_id, DatasetPackage.id.in_(shared_ids))
        )
    else:
        stmt = stmt.where(DatasetPackage.user_id == user_id)
    stmt = stmt.order_by(DatasetPackage.updated_at.desc())
    rows = (await async_session.execute(stmt)).all()
    return [
        DatasetPackageRead(
            **dataset_package.model_dump(),
            owned_by={
                "id": uid,
                "firstname": firstname,
                "lastname": lastname,
                "avatar": avatar,
            },
        )
        for dataset_package, uid, firstname, lastname, avatar in rows
    ]


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
    dataset_package = await authorize_dataset_package(
        async_session, dataset_package_id, user_id, "read"
    )
    return DatasetPackageRead(**dataset_package.model_dump())


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
    """Update a dataset package (owner or editor). Moving the package to a new
    folder (``folder_id``) moves its member layers along with it, so the package
    stays self-contained."""
    dataset_package = await authorize_dataset_package(
        async_session, dataset_package_id, user_id, "write"
    )

    # A move must target a folder the caller owns.
    if package_in.folder_id is not None:
        folder = await async_session.get(Folder, package_in.folder_id)
        if folder is None or folder.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found"
            )

    updated = await crud_dataset_package.update(
        async_session, db_obj=dataset_package, obj_in=package_in
    )

    # Keep member layers in the package's folder (they are hidden, but folder
    # location still drives folder-scoped access checks).
    if package_in.folder_id is not None:
        await async_session.execute(
            sql_update(Layer)
            .where(
                Layer.id.in_(
                    select(DatasetPackageLayerLink.layer_id).where(
                        DatasetPackageLayerLink.dataset_package_id == dataset_package_id
                    )
                )
            )
            .values(folder_id=package_in.folder_id)
        )
        await async_session.commit()

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
    """Delete a dataset package (owner only — this cascades every member layer).
    Member layers are removed via cascade, and their DuckLake data is cleaned up
    via GeoAPI."""
    await authorize_dataset_package(async_session, dataset_package_id, user_id, "owner")

    # Block deletion while another package depends on this one (deleting would
    # break the dependent).
    dependent = (
        await async_session.execute(
            select(DatasetPackageDependencyLink.dataset_package_id)
            .where(
                DatasetPackageDependencyLink.depends_on_package_id
                == dataset_package_id
            )
            .limit(1)
        )
    ).first()
    if dependent is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete a dataset package that another dataset package "
                "depends on. "
                "Remove the dependency first."
            ),
        )

    await crud_dataset_package.delete(
        async_session,
        id=dataset_package_id,
        user_id=user_id,
        access_token=access_token,
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
    await authorize_dataset_package(async_session, dataset_package_id, user_id, "read")
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
    dataset_package = await authorize_dataset_package(async_session, dataset_package_id, user_id, "write")

    # Role must be a valid role key for this package type's spec.
    if payload.role is not None:
        spec = get_spec(dataset_package.dataset_package_type)
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
                detail=f"Role '{payload.role}' is already assigned in this dataset package",
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
    await authorize_dataset_package(async_session, dataset_package_id, user_id, "write")
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
            detail="Layer is not a member of this dataset package",
        )


### Dataset package dependency endpoints
#
# A package can depend on another (e.g. a GTFS package on the street network used
# to build its routable graph / stop-to-street mapping). The allowed dependency
# kinds and required target type come from the type's goatlib spec.


@router.get(
    "/{dataset_package_id}/dependencies",
    summary="List a dataset package's dependencies",
    response_model=List[DatasetPackageDependencyResponse],
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def list_dataset_package_dependencies(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dataset package"),
) -> List[DatasetPackageDependencyResponse]:
    """List the packages this one depends on (owner or shared)."""
    await authorize_dataset_package(async_session, dataset_package_id, user_id, "read")
    rows = (
        await async_session.execute(
            select(DatasetPackageDependencyLink, DatasetPackage)
            .join(
                DatasetPackage,
                DatasetPackage.id == DatasetPackageDependencyLink.depends_on_package_id,
            )
            .where(
                DatasetPackageDependencyLink.dataset_package_id == dataset_package_id
            )
        )
    ).all()
    return [
        DatasetPackageDependencyResponse(
            dependency_kind=link.dependency_kind,
            depends_on_package_id=link.depends_on_package_id,
            depends_on_name=dep.name,
            depends_on_type=str(dep.dataset_package_type),
        )
        for link, dep in rows
    ]


@router.post(
    "/{dataset_package_id}/dependencies",
    summary="Link a dataset package to a dependency (e.g. a street network)",
    response_model=DatasetPackageDependencyResponse,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def add_dataset_package_dependency(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dependent package"),
    payload: DatasetPackageDependencyCreate = Body(...),
) -> DatasetPackageDependencyResponse:
    """Link a package to a dependency. The dependency kind must be declared by
    the package type's spec, and the target package must be of the required
    type. Owner only; upserts the link for the given kind."""
    dataset_package = await authorize_dataset_package(async_session, dataset_package_id, user_id, "write")

    dep_spec = get_spec(dataset_package.dataset_package_type).dependency(
        payload.dependency_kind
    )
    if dep_spec is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{payload.dependency_kind}' is not a valid dependency for "
                f"dataset package type '{get_spec(dataset_package.dataset_package_type).type.value}'"
            ),
        )

    if payload.depends_on_package_id == dataset_package_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A dataset package cannot depend on itself",
        )

    # Target must be accessible to the caller and of the required type.
    target = await authorize_dataset_package(
        async_session, payload.depends_on_package_id, user_id, "read"
    )
    if str(target.dataset_package_type) != dep_spec.package_type.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dependency '{payload.dependency_kind}' requires a package of type "
                f"'{dep_spec.package_type.value}', but the target is "
                f"'{target.dataset_package_type}'"
            ),
        )

    # Upsert: one dependency per (package, kind).
    await async_session.execute(
        sql_delete(DatasetPackageDependencyLink).where(
            and_(
                DatasetPackageDependencyLink.dataset_package_id == dataset_package_id,
                DatasetPackageDependencyLink.dependency_kind == payload.dependency_kind,
            )
        )
    )
    async_session.add(
        DatasetPackageDependencyLink(
            dataset_package_id=dataset_package_id,
            depends_on_package_id=payload.depends_on_package_id,
            dependency_kind=payload.dependency_kind,
        )
    )
    await async_session.commit()
    return DatasetPackageDependencyResponse(
        dependency_kind=payload.dependency_kind,
        depends_on_package_id=payload.depends_on_package_id,
        depends_on_name=target.name,
        depends_on_type=str(target.dataset_package_type),
    )


@router.delete(
    "/{dataset_package_id}/dependencies/{dependency_kind}",
    summary="Remove a dataset package dependency",
    status_code=204,
    dependencies=[Depends(auth_z)],
)
async def delete_dataset_package_dependency(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    dataset_package_id: UUID4 = Path(..., description="The dependent package"),
    dependency_kind: str = Path(..., description="The dependency slot to remove"),
) -> None:
    """Remove a dependency link. Owner only."""
    await authorize_dataset_package(async_session, dataset_package_id, user_id, "write")
    result = await async_session.execute(
        sql_delete(DatasetPackageDependencyLink).where(
            and_(
                DatasetPackageDependencyLink.dataset_package_id == dataset_package_id,
                DatasetPackageDependencyLink.dependency_kind == dependency_kind,
            )
        )
    )
    await async_session.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dependency not found"
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
    """Share a dataset package with a team or organization. Owner or editor."""
    await authorize_dataset_package(async_session, dataset_package_id, user_id, "write")

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
    """List the grants on a dataset package. Owner or editor."""
    await authorize_dataset_package(async_session, dataset_package_id, user_id, "write")
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
    """Remove a specific grant from a dataset package. Owner or editor."""
    await authorize_dataset_package(async_session, dataset_package_id, user_id, "write")
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
