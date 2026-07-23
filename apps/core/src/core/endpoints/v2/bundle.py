import os
import tempfile
from typing import List, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from goatlib.bundles.importers import get_importer
from goatlib.models.bundle import (
    BundleStatus,
    BundleTypeName,
    get_spec,
)
from pydantic import UUID4
from sqlalchemy import and_, or_, select
from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update

from core.core.config import settings
from core.crud.crud_bundle import bundle as crud_bundle
from core.db.models._link_model import (
    BundleDependencyLink,
    BundleLayerLink,
    ResourceGrant,
    UserTeamLink,
)
from core.db.models.bundle import Bundle
from core.db.models.folder import Folder
from core.db.models.layer import Layer
from core.db.models.organization import Organization
from core.db.models.project import Project
from core.db.models.role import Role
from core.db.models.team import Team
from core.db.models.user import User
from core.db.session import AsyncSession
from core.deps.auth import auth, auth_z
from core.endpoints.deps import get_db, get_user_id
from core.schemas.bundle import (
    BundleCreate,
    BundleDependencyCreate,
    BundleDependencyResponse,
    BundleGrantResponse,
    BundleGrantsResponse,
    BundleImportRequest,
    BundleImportResponse,
    BundleMemberCreate,
    BundleMemberResponse,
    BundleRead,
    BundleShareCreate,
    BundleUpdate,
    request_examples,
)
from core.services.geoapi import execute_process
from core.services.s3 import s3_service

RESOURCE_TYPE = "bundle"

router = APIRouter()


def infer_bundle_type(filename: str) -> "BundleTypeName | None":
    """Map an uploaded file name to a bundle type. For now: any file
    named ``*gtfs*.zip`` (case-insensitive) is a GTFS PT network."""
    lower = filename.lower()
    if lower.endswith(".zip") and "gtfs" in lower:
        return BundleTypeName.pt_network_gtfs
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


# Grant roles that confer each access level on a bundle. Access is grant-based
# (like folders): a bundle's own grant, or a grant on the folder it lives in
# (folder grants cascade to the bundle), plus ownership.
_BUNDLE_EDITOR_ROLES = {"bundle-editor", "folder-editor"}
_BUNDLE_VIEWER_ROLES = _BUNDLE_EDITOR_ROLES | {
    "bundle-viewer",
    "folder-viewer",
}

BundleAccess = Literal["read", "write", "owner"]


async def authorize_bundle(
    async_session: AsyncSession,
    bundle_id: UUID,
    user_id: UUID,
    level: BundleAccess,
) -> Bundle:
    """Single authorization gate for a bundle.

    Resolves the caller's effective access from ownership, the bundle's own
    grants, and its folder's grants (folder grants cascade to the bundle), then
    checks it against the required level:

    * ``read``  — viewer or above (view/list),
    * ``write`` — editor or above (update, move, members, dependencies, share),
    * ``owner`` — the bundle owner only (delete — a whole-bundle cascade).

    Returns the bundle, or raises 404 (no access — existence not leaked) /
    403 (has read access but not the required level).
    """
    bundle = await async_session.get(Bundle, bundle_id)
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found"
        )
    if bundle.user_id == user_id:
        return bundle
    if level == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the bundle owner can perform this action",
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
                                ResourceGrant.resource_id == bundle_id,
                            ),
                            and_(
                                ResourceGrant.resource_type == "folder",
                                ResourceGrant.resource_id == bundle.folder_id,
                            ),
                        ),
                        or_(*conds),
                    )
                )
            )
            .scalars()
            .all()
        )
    is_editor = bool(role_names & _BUNDLE_EDITOR_ROLES)
    is_viewer = is_editor or bool(role_names & _BUNDLE_VIEWER_ROLES)
    if level == "write" and is_editor:
        return bundle
    if level == "read" and is_viewer:
        return bundle
    if is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have edit access to this bundle",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found"
    )


### Bundle CRUD endpoints


@router.post(
    "",
    summary="Create a new bundle",
    response_model=BundleRead,
    status_code=201,
    dependencies=[Depends(auth_z)],
)
async def create_bundle(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    package_in: BundleCreate = Body(..., example=request_examples["create"]),
) -> BundleRead:
    """Create a new bundle in a folder the caller owns."""
    folder = await async_session.get(Folder, package_in.folder_id)
    if folder is None or folder.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found"
        )
    package_in.user_id = user_id
    created = await crud_bundle.create(async_session, obj_in=package_in)
    return BundleRead(**created.model_dump())


@router.post(
    "/import",
    summary="Import an uploaded file (e.g. gtfs.zip) as a bundle",
    response_model=BundleImportResponse,
    status_code=202,
    dependencies=[Depends(auth_z)],
)
async def import_bundle(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    access_token: str = Depends(auth),
    payload: BundleImportRequest = Body(...),
) -> BundleImportResponse:
    """Route an uploaded file to the right bundle importer by filename
    (``*gtfs*.zip`` → GTFS PT network), validate it synchronously against the
    type's spec, create the bundle (status=processing) and optional street
    dependency, then ingest the member layers in the background."""
    filename = payload.s3_key.rsplit("/", 1)[-1]
    bundle_type = infer_bundle_type(filename)
    if bundle_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{filename}' is not a recognised bundle upload "
                "(expected e.g. a *gtfs*.zip)"
            ),
        )

    folder = await async_session.get(Folder, payload.folder_id)
    if folder is None or folder.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found"
        )

    # When adding to a project, the caller must own it (guards the project_id
    # that the background job later uses to attach the bundle).
    if payload.project_id is not None:
        project = await async_session.get(Project, payload.project_id)
        if project is None or project.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

    # Synchronous validation: download and check the source against the spec.
    tmp_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
    try:
        s3_service.download_file(settings.S3_BUCKET_NAME, payload.s3_key, tmp_path)
        validation = get_importer(bundle_type).validate(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"Invalid {bundle_type.value} upload",
                "errors": validation.errors,
                "missing_required_roles": validation.missing_required_roles,
            },
        )

    # Validate the optional street-network dependency before creating anything.
    link_street = False
    if payload.street_network_bundle_id is not None:
        dep_spec = get_spec(bundle_type).dependency("street_network")
        if dep_spec is not None:
            target = await authorize_bundle(
                async_session, payload.street_network_bundle_id, user_id, "read"
            )
            if str(target.bundle_type) != dep_spec.bundle_type.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "street_network_bundle_id must reference a "
                        f"'{dep_spec.bundle_type.value}' bundle"
                    ),
                )
            link_street = True

    # Create the bundle shell (processing) + optional dependency, synchronously.
    bundle = Bundle(
        user_id=user_id,
        folder_id=payload.folder_id,
        name=payload.name,
        description=payload.description,
        bundle_type=bundle_type,
        status=BundleStatus.processing,
    )
    async_session.add(bundle)
    await async_session.flush()
    if link_street:
        async_session.add(
            BundleDependencyLink(
                bundle_id=bundle.id,
                depends_on_bundle_id=payload.street_network_bundle_id,
                dependency_kind="street_network",
            )
        )
    await async_session.commit()
    await async_session.refresh(bundle)

    # Trigger the ingest as a Windmill job via the processes service. The job
    # ingests the member layers and flips the bundle status to ready/failed.
    try:
        job_id = await execute_process(
            process_id="bundle_import",
            inputs={
                "bundle_id": str(bundle.id),
                "s3_key": payload.s3_key,
                "bundle_type": bundle_type.value,
                "folder_id": str(payload.folder_id),
                # When uploading from within a project, add the bundle to it once
                # its member layers are ingested.
                **(
                    {"project_id": str(payload.project_id)}
                    if payload.project_id
                    else {}
                ),
            },
            access_token=access_token,
        )
    except Exception:
        # The shell is committed; mark it failed so it isn't stuck "processing".
        bundle.status = BundleStatus.failed
        await async_session.commit()
        raise

    return BundleImportResponse(
        bundle=BundleRead(**bundle.model_dump()), job_id=job_id
    )


@router.get(
    "",
    summary="List the caller's bundles",
    response_model=List[BundleRead],
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def list_bundles(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
) -> List[BundleRead]:
    """List bundles the caller owns or has been shared."""
    team_ids, org_id = await _user_teams_and_org(async_session, user_id)
    conds = _grant_conditions(team_ids, org_id)
    # Join the owner so tiles can show an avatar (same "owned_by" shape as layers).
    stmt = select(
        Bundle,
        User.id,
        User.firstname,
        User.lastname,
        User.avatar,
    ).join(User, User.id == Bundle.user_id)
    if conds:
        shared_ids = select(ResourceGrant.resource_id).where(
            ResourceGrant.resource_type == RESOURCE_TYPE, or_(*conds)
        )
        stmt = stmt.where(
            or_(Bundle.user_id == user_id, Bundle.id.in_(shared_ids))
        )
    else:
        stmt = stmt.where(Bundle.user_id == user_id)
    stmt = stmt.order_by(Bundle.updated_at.desc())
    rows = (await async_session.execute(stmt)).all()
    return [
        BundleRead(
            **bundle.model_dump(),
            owned_by={
                "id": uid,
                "firstname": firstname,
                "lastname": lastname,
                "avatar": avatar,
            },
        )
        for bundle, uid, firstname, lastname, avatar in rows
    ]


@router.get(
    "/{bundle_id}",
    summary="Retrieve a bundle by its ID",
    response_model=BundleRead,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def read_bundle(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle ID"),
) -> BundleRead:
    """Retrieve a bundle the caller owns or has been shared."""
    bundle = await authorize_bundle(
        async_session, bundle_id, user_id, "read"
    )
    return BundleRead(**bundle.model_dump())


@router.put(
    "/{bundle_id}",
    summary="Update a bundle",
    response_model=BundleRead,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def update_bundle(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle ID"),
    package_in: BundleUpdate = Body(...),
) -> BundleRead:
    """Update a bundle (owner or editor). Moving the bundle to a new
    folder (``folder_id``) moves its member layers along with it, so the bundle
    stays self-contained."""
    bundle = await authorize_bundle(
        async_session, bundle_id, user_id, "write"
    )

    # A move must target a folder the caller owns.
    if package_in.folder_id is not None:
        folder = await async_session.get(Folder, package_in.folder_id)
        if folder is None or folder.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found"
            )

    updated = await crud_bundle.update(
        async_session, db_obj=bundle, obj_in=package_in
    )

    # Keep member layers in the bundle's folder (they are hidden, but folder
    # location still drives folder-scoped access checks).
    if package_in.folder_id is not None:
        await async_session.execute(
            sql_update(Layer)
            .where(
                Layer.id.in_(
                    select(BundleLayerLink.layer_id).where(
                        BundleLayerLink.bundle_id == bundle_id
                    )
                )
            )
            .values(folder_id=package_in.folder_id)
        )
        await async_session.commit()

    return BundleRead(**updated.model_dump())


@router.delete(
    "/{bundle_id}",
    summary="Delete a bundle and all its member layers",
    status_code=204,
    dependencies=[Depends(auth_z)],
)
async def delete_bundle(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    access_token: str = Depends(auth),
    bundle_id: UUID4 = Path(..., description="The bundle ID"),
) -> None:
    """Delete a bundle (owner only — this cascades every member layer).
    Member layers are removed via cascade, and their DuckLake data is cleaned up
    via GeoAPI."""
    await authorize_bundle(async_session, bundle_id, user_id, "owner")

    # Block deletion while another bundle depends on this one (deleting would
    # break the dependent).
    dependent = (
        await async_session.execute(
            select(BundleDependencyLink.bundle_id)
            .where(
                BundleDependencyLink.depends_on_bundle_id
                == bundle_id
            )
            .limit(1)
        )
    ).first()
    if dependent is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete a bundle that another bundle "
                "depends on. "
                "Remove the dependency first."
            ),
        )

    await crud_bundle.delete(
        async_session,
        id=bundle_id,
        user_id=user_id,
        access_token=access_token,
    )
    return


### Bundle membership endpoints
#
# Membership lives in the bundle_layer link table: a layer belongs to
# at most one bundle, tagged with the role it plays (a spec role key from
# goatlib). Roles are validated against the bundle type's spec.


@router.get(
    "/{bundle_id}/layers",
    summary="List the layers in a bundle with their roles",
    response_model=List[BundleMemberResponse],
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def list_bundle_layers(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle"),
) -> List[BundleMemberResponse]:
    """List member layers and their roles (owner or shared)."""
    await authorize_bundle(async_session, bundle_id, user_id, "read")
    links = (
        await async_session.execute(
            select(BundleLayerLink).where(
                BundleLayerLink.bundle_id == bundle_id
            )
        )
    ).scalars()
    return [
        BundleMemberResponse(layer_id=link.layer_id, role=link.role)
        for link in links
    ]


@router.post(
    "/{bundle_id}/layers",
    summary="Add a layer to a bundle (or re-tag its role)",
    response_model=BundleMemberResponse,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def add_bundle_layer(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle"),
    payload: BundleMemberCreate = Body(...),
) -> BundleMemberResponse:
    """Add a layer to the bundle with a role, or update the role if the layer
    is already a member. Owner only."""
    bundle = await authorize_bundle(async_session, bundle_id, user_id, "write")

    # Role must be a valid role key for this bundle type's spec.
    if payload.role is not None:
        spec = get_spec(bundle.bundle_type)
        if payload.role not in spec.role_keys():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid role '{payload.role}' for bundle type "
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
            select(BundleLayerLink).where(
                BundleLayerLink.layer_id == payload.layer_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.bundle_id != bundle_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Layer already belongs to another bundle",
        )

    # A role can be filled by only one layer within the bundle.
    if payload.role is not None:
        role_taken = (
            await async_session.execute(
                select(BundleLayerLink.id).where(
                    BundleLayerLink.bundle_id == bundle_id,
                    BundleLayerLink.role == payload.role,
                    BundleLayerLink.layer_id != payload.layer_id,
                )
            )
        ).first()
        if role_taken is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Role '{payload.role}' is already assigned in this bundle",
            )

    if existing is not None:
        existing.role = payload.role
        link = existing
    else:
        link = BundleLayerLink(
            bundle_id=bundle_id,
            layer_id=payload.layer_id,
            role=payload.role,
        )
        async_session.add(link)
    await async_session.commit()
    return BundleMemberResponse(layer_id=link.layer_id, role=link.role)


@router.delete(
    "/{bundle_id}/layers/{layer_id}",
    summary="Remove a layer from a bundle",
    status_code=204,
    dependencies=[Depends(auth_z)],
)
async def remove_bundle_layer(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle"),
    layer_id: UUID4 = Path(..., description="The member layer to remove"),
) -> None:
    """Remove a layer from the bundle (the layer itself is not deleted; it
    becomes a standalone layer again). Owner only."""
    await authorize_bundle(async_session, bundle_id, user_id, "write")
    result = await async_session.execute(
        sql_delete(BundleLayerLink).where(
            and_(
                BundleLayerLink.bundle_id == bundle_id,
                BundleLayerLink.layer_id == layer_id,
            )
        )
    )
    await async_session.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layer is not a member of this bundle",
        )


### Bundle dependency endpoints
#
# A bundle can depend on another (e.g. a GTFS bundle on the street network used
# to build its routable graph / stop-to-street mapping). The allowed dependency
# kinds and required target type come from the type's goatlib spec.


@router.get(
    "/{bundle_id}/dependencies",
    summary="List a bundle's dependencies",
    response_model=List[BundleDependencyResponse],
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def list_bundle_dependencies(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle"),
) -> List[BundleDependencyResponse]:
    """List the bundles this one depends on (owner or shared)."""
    await authorize_bundle(async_session, bundle_id, user_id, "read")
    rows = (
        await async_session.execute(
            select(BundleDependencyLink, Bundle)
            .join(
                Bundle,
                Bundle.id == BundleDependencyLink.depends_on_bundle_id,
            )
            .where(
                BundleDependencyLink.bundle_id == bundle_id
            )
        )
    ).all()
    return [
        BundleDependencyResponse(
            dependency_kind=link.dependency_kind,
            depends_on_bundle_id=link.depends_on_bundle_id,
            depends_on_name=dep.name,
            depends_on_type=str(dep.bundle_type),
        )
        for link, dep in rows
    ]


@router.post(
    "/{bundle_id}/dependencies",
    summary="Link a bundle to a dependency (e.g. a street network)",
    response_model=BundleDependencyResponse,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def add_bundle_dependency(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The dependent bundle"),
    payload: BundleDependencyCreate = Body(...),
) -> BundleDependencyResponse:
    """Link a bundle to a dependency. The dependency kind must be declared by
    the bundle type's spec, and the target bundle must be of the required
    type. Owner only; upserts the link for the given kind."""
    bundle = await authorize_bundle(async_session, bundle_id, user_id, "write")

    dep_spec = get_spec(bundle.bundle_type).dependency(
        payload.dependency_kind
    )
    if dep_spec is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{payload.dependency_kind}' is not a valid dependency for "
                f"bundle type '{get_spec(bundle.bundle_type).type.value}'"
            ),
        )

    if payload.depends_on_bundle_id == bundle_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A bundle cannot depend on itself",
        )

    # Target must be accessible to the caller and of the required type.
    target = await authorize_bundle(
        async_session, payload.depends_on_bundle_id, user_id, "read"
    )
    if str(target.bundle_type) != dep_spec.bundle_type.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dependency '{payload.dependency_kind}' requires a bundle of type "
                f"'{dep_spec.bundle_type.value}', but the target is "
                f"'{target.bundle_type}'"
            ),
        )

    # Upsert: one dependency per (bundle, kind).
    await async_session.execute(
        sql_delete(BundleDependencyLink).where(
            and_(
                BundleDependencyLink.bundle_id == bundle_id,
                BundleDependencyLink.dependency_kind == payload.dependency_kind,
            )
        )
    )
    async_session.add(
        BundleDependencyLink(
            bundle_id=bundle_id,
            depends_on_bundle_id=payload.depends_on_bundle_id,
            dependency_kind=payload.dependency_kind,
        )
    )
    await async_session.commit()
    return BundleDependencyResponse(
        dependency_kind=payload.dependency_kind,
        depends_on_bundle_id=payload.depends_on_bundle_id,
        depends_on_name=target.name,
        depends_on_type=str(target.bundle_type),
    )


@router.delete(
    "/{bundle_id}/dependencies/{dependency_kind}",
    summary="Remove a bundle dependency",
    status_code=204,
    dependencies=[Depends(auth_z)],
)
async def delete_bundle_dependency(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The dependent bundle"),
    dependency_kind: str = Path(..., description="The dependency slot to remove"),
) -> None:
    """Remove a dependency link. Owner only."""
    await authorize_bundle(async_session, bundle_id, user_id, "write")
    result = await async_session.execute(
        sql_delete(BundleDependencyLink).where(
            and_(
                BundleDependencyLink.bundle_id == bundle_id,
                BundleDependencyLink.dependency_kind == dependency_kind,
            )
        )
    )
    await async_session.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dependency not found"
        )


### Bundle sharing endpoints
#
# A bundle is the sole sharing unit for its member layers: sharing a
# bundle with a team/organisation grants access to every member layer (derived
# at authorization time in check_layer.sql). Member layers cannot be shared
# individually (enforced in the layer share endpoint).


@router.post(
    "/{bundle_id}/share",
    summary="Share a bundle with a team or organization",
    response_model=BundleGrantsResponse,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def share_bundle(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle to share"),
    payload: BundleShareCreate = Body(...),
) -> BundleGrantsResponse:
    """Share a bundle with a team or organization. Owner or editor."""
    await authorize_bundle(async_session, bundle_id, user_id, "write")

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
                ResourceGrant.resource_id == bundle_id,
                ResourceGrant.grantee_type == payload.grantee_type,
                ResourceGrant.grantee_id == payload.grantee_id,
            )
        )
    )
    async_session.add(
        ResourceGrant(
            resource_type=RESOURCE_TYPE,
            resource_id=bundle_id,
            grantee_type=payload.grantee_type,
            grantee_id=payload.grantee_id,
            role_id=role.id,
            granted_by=user_id,
        )
    )
    await async_session.commit()
    return await _get_grants_response(async_session, bundle_id)


@router.get(
    "/{bundle_id}/share",
    summary="List current grants for a bundle",
    response_model=BundleGrantsResponse,
    status_code=200,
    dependencies=[Depends(auth_z)],
)
async def get_bundle_grants(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle"),
) -> BundleGrantsResponse:
    """List the grants on a bundle. Owner or editor."""
    await authorize_bundle(async_session, bundle_id, user_id, "write")
    return await _get_grants_response(async_session, bundle_id)


@router.delete(
    "/{bundle_id}/share/{grantee_type}/{grantee_id}",
    summary="Remove a grant from a bundle",
    status_code=204,
    dependencies=[Depends(auth_z)],
)
async def delete_bundle_grant(
    *,
    async_session: AsyncSession = Depends(get_db),
    user_id: UUID4 = Depends(get_user_id),
    bundle_id: UUID4 = Path(..., description="The bundle"),
    grantee_type: str = Path(..., description="team or organization"),
    grantee_id: UUID4 = Path(..., description="The team or organization ID"),
) -> None:
    """Remove a specific grant from a bundle. Owner or editor."""
    await authorize_bundle(async_session, bundle_id, user_id, "write")
    result = await async_session.execute(
        sql_delete(ResourceGrant).where(
            and_(
                ResourceGrant.resource_type == RESOURCE_TYPE,
                ResourceGrant.resource_id == bundle_id,
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
    async_session: AsyncSession, bundle_id: UUID
) -> BundleGrantsResponse:
    """Fetch all grants for a bundle, enriched with grantee display names."""
    rows = (
        await async_session.execute(
            select(ResourceGrant, Role)
            .join(Role, Role.id == ResourceGrant.role_id)
            .where(
                ResourceGrant.resource_type == RESOURCE_TYPE,
                ResourceGrant.resource_id == bundle_id,
            )
        )
    ).all()

    enriched: list[BundleGrantResponse] = []
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
            BundleGrantResponse(
                grantee_type=grant.grantee_type,
                grantee_id=grant.grantee_id,
                grantee_name=name,
                role=role.name,
            )
        )
    return BundleGrantsResponse(grants=enriched)
