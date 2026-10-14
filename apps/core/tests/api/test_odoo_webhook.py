import pytest
from core.core.config import settings
from tests.billing import enable_billing
from tests.utils import make_organization


@pytest.mark.asyncio
async def test_odoo_entitlement_applies_and_resets(client, db_session, monkeypatch):
    enable_billing(monkeypatch)
    org = make_organization(total_credits=1000, used_credits=900)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    resp = await client.post(
        f"{settings.API_V2_STR}/webhooks/odoo/entitlement",
        headers={"X-Webhook-Secret": "shh"},
        json={
            "organization_id": str(org.id),
            "total_credits": 5000,
            "extras": ["white_label"],
            "plan_renewal_date": "2026-08-01T00:00:00",
            "reset_usage": True,
        },
    )
    assert resp.status_code == 200
    await db_session.refresh(org)
    assert float(org.total_credits) == 5000
    assert float(org.used_credits) == 0
    assert org.extras == ["white_label"]


@pytest.mark.asyncio
async def test_trial_webhook_expired_suspends(client, db_session, monkeypatch):
    enable_billing(monkeypatch)
    org = make_organization(on_trial=True)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    resp = await client.post(
        f"{settings.API_V2_STR}/webhooks/trial",
        headers={"X-Webhook-Secret": "shh"},
        json={"organization_id": str(org.id), "stage": "expired"},
    )
    assert resp.status_code == 200
    await db_session.refresh(org)
    assert org.suspended is True
    assert org.on_trial is True  # still a trial, just expired


@pytest.mark.asyncio
async def test_trial_webhook_expiring_does_not_suspend(client, db_session, monkeypatch):
    enable_billing(monkeypatch)
    org = make_organization(on_trial=True)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    resp = await client.post(
        f"{settings.API_V2_STR}/webhooks/trial",
        headers={"X-Webhook-Secret": "shh"},
        json={"organization_id": str(org.id), "stage": "expiring"},
    )
    assert resp.status_code == 200
    await db_session.refresh(org)
    assert org.suspended is False


@pytest.mark.asyncio
async def test_trial_webhook_rejects_unknown_stage(client, monkeypatch):
    enable_billing(monkeypatch)
    resp = await client.post(
        f"{settings.API_V2_STR}/webhooks/trial",
        headers={"X-Webhook-Secret": "shh"},
        json={"organization_id": "x", "stage": "nonsense"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_odoo_entitlement_bad_secret(client, monkeypatch):
    enable_billing(monkeypatch)
    resp = await client.post(
        f"{settings.API_V2_STR}/webhooks/odoo/entitlement",
        headers={"X-Webhook-Secret": "wrong"},
        json={"organization_id": "x"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhooks_do_not_exist_without_billing(client, db_session, monkeypatch):
    # Self-hosted: no Odoo settings, the routes answer 404 even with a secret.
    monkeypatch.setattr(settings, "ODOO_URL", None)
    monkeypatch.setattr(settings, "ODOO_WEBHOOK_SECRET", "shh")
    org = make_organization(on_trial=True)
    db_session.add(org)
    await db_session.commit()

    for path, body in (
        ("/webhooks/odoo/entitlement", {"organization_id": str(org.id)}),
        ("/webhooks/trial", {"organization_id": str(org.id), "stage": "expired"}),
    ):
        resp = await client.post(
            f"{settings.API_V2_STR}{path}",
            headers={"X-Webhook-Secret": "shh"},
            json=body,
        )
        assert resp.status_code == 404, path


@pytest.mark.asyncio
async def test_webhook_refuses_a_wrong_secret(client, db_session, monkeypatch):
    enable_billing(monkeypatch)
    org = make_organization(on_trial=True)
    db_session.add(org)
    await db_session.commit()

    resp = await client.post(
        f"{settings.API_V2_STR}/webhooks/trial",
        headers={"X-Webhook-Secret": "wrong"},
        json={"organization_id": str(org.id), "stage": "expired"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_conversion_starts_the_monthly_credit_period(
    client, db_session, monkeypatch
):
    from datetime import datetime, timedelta

    enable_billing(monkeypatch)
    org = make_organization(on_trial=True, total_credits=10000, used_credits=8000)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    resp = await client.post(
        f"{settings.API_V2_STR}/webhooks/odoo/entitlement",
        headers={"X-Webhook-Secret": "shh"},
        json={
            "organization_id": str(org.id),
            "on_trial": False,
            "total_credits": 25000,
            "plan_renewal_date": "2027-10-14T00:00:00",
            "reset_usage": False,
        },
    )
    assert resp.status_code == 200
    await db_session.refresh(org)
    assert org.on_trial is False
    assert float(org.used_credits) == 0
    # monthly, not with the yearly renewal
    assert (
        timedelta(days=27) < org.credits_reset_at - datetime.now() < timedelta(days=32)
    )


@pytest.mark.asyncio
async def test_a_trial_change_from_odoo_starts_no_credit_period(
    client, db_session, monkeypatch
):
    enable_billing(monkeypatch)
    org = make_organization(on_trial=True, total_credits=10000, used_credits=300)
    db_session.add(org)
    await db_session.commit()

    resp = await client.post(
        f"{settings.API_V2_STR}/webhooks/odoo/entitlement",
        headers={"X-Webhook-Secret": "shh"},
        json={
            "organization_id": str(org.id),
            "plan_renewal_date": "2026-12-01T23:59:59",
            "suspended": False,
            "reset_usage": False,
        },
    )
    assert resp.status_code == 200
    await db_session.refresh(org)
    assert org.on_trial is True
    assert org.credits_reset_at is None
    assert float(org.used_credits) == 300
