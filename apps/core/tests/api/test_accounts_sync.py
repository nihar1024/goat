"""Sign-ups and trials reported to Odoo's goat_accounts module (a fake Odoo here)."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from core.accounts import sync
from core.core.config import settings
from core.db.models.user import User
from tests.billing import enable_billing
from tests.utils import make_organization


class FakeOdoo:
    def __init__(self) -> None:
        self.ops: list[dict[str, Any]] = []

    async def call(self, model: str, method: str, **kwargs: Any) -> Any:
        if method == "search":
            return [42]
        context = kwargs["context"]
        self.ops.append(context)
        if context["goat_op"] == "sign_up":
            return {"goat_contact_id": 7}
        return {"goat_company_id": 9, "goat_contact_id": 7}


@pytest.fixture
def odoo(monkeypatch: pytest.MonkeyPatch) -> FakeOdoo:
    enable_billing(monkeypatch)
    monkeypatch.setattr(settings, "ODOO_BILLING_API_KEY", "key")
    fake = FakeOdoo()
    monkeypatch.setattr(sync, "_odoo", lambda: fake)
    monkeypatch.setattr(sync, "_action_id", None)
    sync._last_try.clear()
    return fake


async def _settle() -> None:
    while sync._tasks:
        await asyncio.gather(*list(sync._tasks))


async def _user(db_session, **values: Any) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4().hex[:8]}@stadt-beispiel.de",
        firstname="Anna",
        lastname="Keller",
        **values,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_a_verified_user_becomes_a_contact(db_session, odoo):
    user = await _user(db_session, newsletter_subscribe=True)
    sync.report_sign_up(user, {"email_verified": True})
    await _settle()

    (op,) = odoo.ops
    assert op["goat_op"] == "sign_up"
    assert op["goat_user_id"] == str(user.id)
    assert op["goat_name"] == "Anna Keller"
    assert op["goat_marketing_consent"] is True
    await db_session.refresh(user)
    assert user.odoo_contact_id == 7


@pytest.mark.asyncio
async def test_unverified_or_known_users_are_not_reported(db_session, odoo):
    unverified = await _user(db_session)
    known = await _user(db_session, odoo_contact_id=3)
    sync.report_sign_up(unverified, {"email_verified": False})
    sync.report_sign_up(known, {"email_verified": True})
    await _settle()
    assert odoo.ops == []


@pytest.mark.asyncio
async def test_a_user_is_tried_once_per_retry_window(db_session, odoo):
    user = await _user(db_session)
    sync.report_sign_up(user, {"email_verified": True})
    sync.report_sign_up(user, {"email_verified": True})
    await _settle()
    assert len(odoo.ops) == 1


@pytest.mark.asyncio
async def test_nothing_is_reported_without_the_bridge_key(
    db_session, odoo, monkeypatch
):
    monkeypatch.setattr(settings, "ODOO_BILLING_API_KEY", None)
    user = await _user(db_session)
    sync.report_sign_up(user, {"email_verified": True})
    await _settle()
    assert odoo.ops == []


@pytest.mark.asyncio
async def test_a_trial_starts_in_odoo_and_links_the_company(db_session, odoo):
    user = await _user(db_session)
    end = datetime.now() + timedelta(days=30)
    org = make_organization(on_trial=True, plan_renewal_date=end, name="Stadt Beispiel")
    db_session.add(org)
    await db_session.commit()

    sync.report_trial(org, user.id)
    await _settle()

    sign_up, trial = odoo.ops
    assert sign_up["goat_op"] == "sign_up"
    assert trial["goat_op"] == "start_trial"
    assert trial["goat_organization_id"] == str(org.id)
    assert trial["goat_organization_name"] == "Stadt Beispiel"
    assert trial["goat_trial_end"] == end.date().isoformat()
    await db_session.refresh(org)
    assert org.odoo_company_id == 9


@pytest.mark.asyncio
async def test_a_failing_odoo_never_reaches_the_caller(db_session, odoo, monkeypatch):
    async def down(*args: Any, **kwargs: Any) -> Any:
        from core.odoo import OdooUnavailable

        raise OdooUnavailable("down")

    monkeypatch.setattr(odoo, "call", down)
    user = await _user(db_session)
    sync.report_sign_up(user, {"email_verified": True})
    await _settle()  # logged, not raised
    await db_session.refresh(user)
    assert user.odoo_contact_id is None


@pytest.mark.asyncio
async def test_a_suspension_is_reported_to_odoo(db_session, odoo):
    org = make_organization(on_trial=True, suspended=True)
    db_session.add(org)
    await db_session.commit()

    sync.report_suspension(org)
    await _settle()

    (op,) = odoo.ops
    assert op == {
        "goat_op": "status",
        "goat_organization_id": str(org.id),
        "goat_suspended": True,
        "goat_on_trial": True,
    }
