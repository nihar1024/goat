import asyncio
import logging
import time
from collections.abc import Coroutine
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select

from core import odoo
from core.core.config import settings
from core.db.models.organization import Organization
from core.db.models.system_setting import SystemSetting
from core.db.models.user import User
from core.db.session import session_manager
from core.schemas.system_setting import default_system_settings

logger = logging.getLogger(__name__)

ALLOWED_CALLS = frozenset(
    {("ir.actions.server", "search"), ("ir.actions.server", "run")}
)
LANGUAGES = {"de": "de_DE", "en": "en_US"}
RETRY_SECONDS = 600

_client: odoo.OdooClient | None = None
_action_id: int | None = None
_tasks: set[asyncio.Task[None]] = set()
_last_try: dict[UUID, float] = {}


def _odoo() -> odoo.OdooClient:
    global _client
    if _client is None:
        assert settings.ODOO_URL and settings.ODOO_DB and settings.ODOO_BILLING_API_KEY
        _client = odoo.OdooClient(
            settings.ODOO_URL,
            settings.ODOO_DB,
            settings.ODOO_BILLING_API_KEY,
            allowed_calls=ALLOWED_CALLS,
            ca_bundle=settings.GOAT_CA_BUNDLE,
        )
    return _client


async def _run(op: str, **context: Any) -> dict[str, Any]:
    """Run one operation of the server action as the bridge user."""
    global _action_id
    client = _odoo()
    if _action_id is None:
        found = await client.call(
            "ir.actions.server",
            "search",
            domain=[("name", "=", settings.ODOO_ACCOUNTS_ACTION)],
            limit=1,
        )
        if not found:
            raise odoo.OdooRejected(
                f"no server action {settings.ODOO_ACCOUNTS_ACTION!r}"
            )
        _action_id = int(found[0])
    result = await client.call(
        "ir.actions.server", "run", ids=[_action_id], context={"goat_op": op, **context}
    )
    return result or {}


def _in_background(work: Coroutine[Any, Any, None]) -> None:
    """Run after the caller's request; failures are logged, never raised."""

    async def guarded() -> None:
        try:
            await work
        except odoo.OdooError as exc:
            logger.warning("accounts sync: Odoo refused or is down: %s", exc)
        except Exception:  # noqa: BLE001 - the sync must never break GOAT
            logger.exception("accounts sync failed")

    task = asyncio.get_running_loop().create_task(guarded())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _odoo_language(value: object) -> str | None:
    """'de', 'de-DE' or 'de_DE' -> 'de_DE'; None when unknown."""
    code = str(value or "").strip().lower().replace("-", "_").split("_")[0]
    return LANGUAGES.get(code)


async def _language(session: Any, user_id: UUID, hint: str | None) -> str | None:
    """The person's language for Odoo's mails, the one GOAT shows them: chosen
    on the sign-up page (Keycloak's `locale` claim), else their GOAT setting,
    else GOAT's default."""
    if _odoo_language(hint):
        return _odoo_language(hint)
    setting = (
        await session.execute(
            select(SystemSetting.preferred_language).where(
                SystemSetting.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    return _odoo_language(getattr(setting, "value", setting)) or _odoo_language(
        default_system_settings.preferred_language.value
    )


async def _sign_up(user_id: UUID, locale: str | None = None) -> int | None:
    """Report the user; returns their contact id in Odoo. The language goes
    along the first time and when a locale is given (sign-up page, a change
    in GOAT's settings); later reports leave Odoo's alone."""
    async with session_manager.session() as session:
        user = await session.get(User, user_id)
        if user is None:
            return None
        name = " ".join(p for p in (user.firstname, user.lastname) if p) or user.email
        lang = (
            None
            if user.odoo_contact_id and locale is None
            else await _language(session, user.id, locale)
        )
        logger.info("Odoo: reporting user %s, language %s", user.id, lang or "-")
        result = await _run(
            "sign_up",
            goat_user_id=str(user.id),
            goat_name=name,
            goat_email=user.email,
            goat_marketing_consent=bool(user.newsletter_subscribe),
            **({"goat_lang": lang} if lang else {}),
        )
        contact_id = result.get("goat_contact_id")
        if contact_id and user.odoo_contact_id != contact_id:
            user.odoo_contact_id = int(contact_id)
            await session.commit()
        return contact_id


def report_sign_up(user: User, token: dict) -> None:
    """On a request of a user Odoo does not know yet, with a verified email."""
    if (
        not settings.accounts_sync_enabled
        or user.odoo_contact_id
        or not token.get("email_verified")
    ):
        return
    assert user.id is not None
    now = time.monotonic()
    if now - _last_try.get(user.id, -RETRY_SECONDS) < RETRY_SECONDS:
        return
    _last_try[user.id] = now

    locale = token.get("locale")

    async def work() -> None:
        await _sign_up(user.id, locale)

    _in_background(work())


def report_language(user_id: UUID, language: object) -> None:
    """The user changed GOAT's language: Odoo's mails follow, once Odoo knows
    the user (the sign-up report itself needs a verified email)."""
    locale = str(getattr(language, "value", language) or "")
    if not settings.accounts_sync_enabled or not _odoo_language(locale):
        return

    async def work() -> None:
        async with session_manager.session() as session:
            user = await session.get(User, user_id)
            known = user is not None and user.odoo_contact_id
        if known:
            await _sign_up(user_id, locale)

    _in_background(work())


def report_trial(organization: Organization, owner_id: UUID) -> None:
    """The owner created an organization that starts a trial."""
    if not settings.accounts_sync_enabled or not organization.on_trial:
        return
    org_id, name = organization.id, organization.name
    end = organization.plan_renewal_date
    if end is None:
        return

    async def work() -> None:
        await _sign_up(owner_id)  # newsletter consent comes with the organization form
        result = await _run(
            "start_trial",
            goat_user_id=str(owner_id),
            goat_organization_id=str(org_id),
            goat_organization_name=name,
            goat_trial_start=date.today().isoformat(),
            goat_trial_end=end.date().isoformat(),
        )
        await _store_company(org_id, result.get("goat_company_id"))

    _in_background(work())


def report_suspension(organization: Organization) -> None:
    """GOAT changed the organization's state itself: suspended or reactivated
    (its trial ended), or converted from trial to subscription. Odoo shows it
    on the company, without sending it back; a converted organization's
    people leave the trial campaign."""
    if not settings.accounts_sync_enabled:
        return
    org_id = organization.id
    suspended, on_trial = bool(organization.suspended), bool(organization.on_trial)

    async def work() -> None:
        await _run(
            "status",
            goat_organization_id=str(org_id),
            goat_suspended=suspended,
            goat_on_trial=on_trial,
        )

    _in_background(work())


def report_join(user_id: UUID, organization: Organization, role: str) -> None:
    """An invited member joined an organization Odoo knows."""
    if not settings.accounts_sync_enabled:
        return
    org_id, name = organization.id, organization.name

    async def work() -> None:
        if await _sign_up(user_id) is None:
            return
        result = await _run(
            "join",
            goat_user_id=str(user_id),
            goat_organization_id=str(org_id),
            goat_organization_name=name,
            goat_role=role
            if role in ("owner", "admin", "editor", "viewer")
            else "editor",
        )
        await _store_company(org_id, result.get("goat_company_id"))

    _in_background(work())


async def _store_company(org_id: UUID, company_id: Any) -> None:
    if not company_id:
        return
    async with session_manager.session() as session:
        organization = await session.get(Organization, org_id)
        if organization is not None and organization.odoo_company_id != int(company_id):
            organization.odoo_company_id = int(company_id)
            await session.commit()
