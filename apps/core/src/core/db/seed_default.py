import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.core.config import settings
from core.crud.crud_organization import SELF_HOSTED_PLAN_METADATA
from core.db.models import Organization, Role, User, UserRoleLink
from core.db.models.folder import Folder
from core.db.session import session_manager


async def seed_default_user_org(session: AsyncSession) -> None:
    """Provision the default identity for deployments running with AUTH=False.

    Creates the default user, its organization (with self-hosted quotas), the
    organization-owner role assignment and a home folder. Idempotent — every
    object is created only if missing, so re-running on each deploy is safe.
    Requires the roles from ``seed_roles`` to be present.
    """
    user_id = UUID(settings.DEFAULT_USER_ID)

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=user_id,
            email=settings.DEFAULT_USER_EMAIL,
            firstname=settings.DEFAULT_USER_FIRSTNAME,
            lastname=settings.DEFAULT_USER_LASTNAME,
            avatar=settings.USER_DEFAULT_AVATAR,
        )
        session.add(user)
        await session.flush()

    if user.organization_id is None:
        organization = Organization(
            name=settings.DEFAULT_ORGANIZATION_NAME,
            avatar=settings.ORGANIZATION_DEFAULT_AVATAR,
            on_trial=False,
            total_credits=SELF_HOSTED_PLAN_METADATA["credits"],
            total_storage=SELF_HOSTED_PLAN_METADATA["storage"],
            total_projects=SELF_HOSTED_PLAN_METADATA["projects"],
            total_editors=SELF_HOSTED_PLAN_METADATA["editors"],
            total_viewers=SELF_HOSTED_PLAN_METADATA["viewers"],
            plan_name=SELF_HOSTED_PLAN_METADATA["plan_name"],
            type="other",
            size="1-10",
            industry="other",
            department="general",
            use_case="other",
            phone_number="+0000000000",
            location="local",
            region="EU",
            contact_user_id=user_id,
            stripe_id="",
            suspended=False,
        )
        session.add(organization)
        await session.flush()
        user.organization_id = organization.id

    owner_role_id = (
        await session.execute(select(Role.id).where(Role.name == "organization-owner"))
    ).scalar_one()
    has_owner_role = (
        await session.execute(
            select(UserRoleLink.id).where(
                UserRoleLink.user_id == user_id,
                UserRoleLink.role_id == owner_role_id,
            )
        )
    ).scalar_one_or_none()
    if has_owner_role is None:
        session.add(UserRoleLink(user_id=user_id, role_id=owner_role_id))

    has_home_folder = (
        await session.execute(
            select(Folder.id).where(Folder.user_id == user_id, Folder.name == "home")
        )
    ).scalar_one_or_none()
    if has_home_folder is None:
        session.add(Folder(user_id=user_id, name="home"))

    await session.commit()


async def seed_catalog_identity(session: AsyncSession) -> None:
    """Provision the system identity that owns promoted catalog layers.

    Runs in every environment (the default identity above is AUTH=False-only):
    promote-on-use needs an owner for the shared, read-only layer rows, and
    `customer.layer.user_id` is NOT NULL. The organization gets effectively
    unlimited quotas — its storage is the shared catalog cache, billed to
    nobody. Idempotent, like the seeds above.
    """
    user_id = UUID(settings.CATALOG_USER_ID)

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=user_id,
            email=settings.CATALOG_USER_EMAIL,
            firstname="GOAT",
            lastname="Catalog",
            avatar=settings.USER_DEFAULT_AVATAR,
        )
        session.add(user)
        await session.flush()

    if user.organization_id is None:
        organization = Organization(
            name=settings.CATALOG_ORGANIZATION_NAME,
            avatar=settings.ORGANIZATION_DEFAULT_AVATAR,
            on_trial=False,
            # Not a plan: the quota ceiling for a shared cache is "none", and
            # the enforcement compares against these numbers.
            total_credits=2**31 - 1,
            total_storage=2**31 - 1,
            total_projects=2**31 - 1,
            total_editors=2**31 - 1,
            total_viewers=2**31 - 1,
            plan_name=settings.DEFAULT_PLAN_NAME,
            type="other",
            size="1-10",
            industry="other",
            department="general",
            use_case="other",
            phone_number="+0000000000",
            location="system",
            region="EU",
            contact_user_id=user_id,
            stripe_id="",
            suspended=False,
        )
        session.add(organization)
        await session.flush()
        user.organization_id = organization.id

    owner_role_id = (
        await session.execute(select(Role.id).where(Role.name == "organization-owner"))
    ).scalar_one()
    has_owner_role = (
        await session.execute(
            select(UserRoleLink.id).where(
                UserRoleLink.user_id == user_id,
                UserRoleLink.role_id == owner_role_id,
            )
        )
    ).scalar_one_or_none()
    if has_owner_role is None:
        session.add(UserRoleLink(user_id=user_id, role_id=owner_role_id))

    folder_id = UUID(settings.CATALOG_FOLDER_ID)
    has_folder = (
        await session.execute(select(Folder.id).where(Folder.id == folder_id))
    ).scalar_one_or_none()
    if has_folder is None:
        session.add(Folder(id=folder_id, user_id=user_id, name="catalog"))

    await session.commit()


async def main() -> None:
    session_manager.init(settings.ASYNC_SQLALCHEMY_DATABASE_URI)
    try:
        async with session_manager.session() as session:
            await seed_default_user_org(session)
    finally:
        await session_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
