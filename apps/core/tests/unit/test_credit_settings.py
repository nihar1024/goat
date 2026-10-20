import pytest
from core.core.config import Settings, settings
from tests.billing import TERMS


def test_credit_operational_settings():
    assert settings.MAX_TOOL_RUNTIME_SECONDS == 1800
    # None == unlimited for self-hosted
    assert settings.DEFAULT_QUOTA_CREDITS is None


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """What a developer's shell exports must not decide these tests."""
    for name in (
        *TERMS,
        "BILLING_ENABLED",
        "BILLING_WEBHOOK_SECRET",
        "ODOO_URL",
        "ODOO_DB",
        "ODOO_ACCOUNTS_API_KEY",
        "ODOO_SUPPORT_API_KEY",
        "ODOO_SUPPORT_TEAM_ID",
    ):
        monkeypatch.delenv(name, raising=False)


def _settings(**values) -> Settings:
    return Settings(_env_file=None, AUTH=False, **values)  # type: ignore[call-arg]


def test_billing_has_no_commercial_defaults():
    # The trial and the credit rates are the operator's terms, not GOAT's.
    off = _settings()
    assert off.BILLING_ENABLED is False
    for name in TERMS:
        assert getattr(off, name) is None


def test_billing_off_needs_none_of_them():
    assert _settings(BILLING_ENABLED=False).billing_enabled is False


def test_billing_on_names_every_missing_setting():
    with pytest.raises(ValueError) as error:
        _settings(BILLING_ENABLED=True, TRIAL_DAYS=14)
    message = str(error.value)
    for name in ("BILLING_WEBHOOK_SECRET", *TERMS):
        assert (name in message) is (name != "TRIAL_DAYS")


def test_billing_on_with_everything_is_enabled():
    on = _settings(BILLING_ENABLED=True, BILLING_WEBHOOK_SECRET="s", **TERMS)
    assert on.billing_enabled is True


def test_empty_values_count_as_unset():
    with pytest.raises(ValueError, match="TRIAL_DAYS"):
        _settings(
            BILLING_ENABLED=True,
            BILLING_WEBHOOK_SECRET="s",
            **{**TERMS, "TRIAL_DAYS": ""},
        )


def test_an_empty_billing_switch_is_off(monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "")
    assert _settings().billing_enabled is False


def test_billing_does_not_depend_on_odoo():
    on = _settings(BILLING_ENABLED=True, BILLING_WEBHOOK_SECRET="s", **TERMS)
    assert on.ODOO_URL is None and on.billing_enabled
    assert on.accounts_sync_enabled is False


def test_support_alone_leaves_billing_off():
    support = _settings(
        ODOO_URL="https://odoo.test",
        ODOO_DB="db",
        ODOO_SUPPORT_API_KEY="k",
        ODOO_SUPPORT_TEAM_ID=1,
    )
    assert support.support_enabled is True
    assert support.billing_enabled is False
    assert support.accounts_sync_enabled is False


def test_accounts_sync_needs_the_odoo_connection_and_its_key():
    base = {"BILLING_ENABLED": True, "BILLING_WEBHOOK_SECRET": "s", **TERMS}
    assert _settings(**base).accounts_sync_enabled is False
    partial = _settings(**base, ODOO_URL="https://odoo.test", ODOO_DB="db")
    assert partial.accounts_sync_enabled is False
    full = _settings(
        **base,
        ODOO_URL="https://odoo.test",
        ODOO_DB="db",
        ODOO_ACCOUNTS_API_KEY="k",
    )
    assert full.accounts_sync_enabled is True


def test_the_trial_reads_the_settings_at_the_time_of_use(monkeypatch):
    from core.crud.crud_organization import trial_quotas
    from tests.billing import enable_billing

    enable_billing(monkeypatch)
    assert trial_quotas()["credits"] == TERMS["TRIAL_QUOTA_CREDITS"]
    assert trial_quotas()["editors"] == TERMS["TRIAL_QUOTA_EDITORS"]
