from core.core.config import settings


def test_credit_operational_settings():
    # Conversion rates are NOT settings (they live in customer.credit_rate);
    # only operational knobs are here.
    assert not hasattr(settings, "CREDIT_RATE_COMPUTE_PER_MINUTE")
    assert settings.MAX_TOOL_RUNTIME_SECONDS == 1800
    # None == unlimited for self-hosted
    assert settings.DEFAULT_QUOTA_CREDITS is None


def test_trial_defaults():
    # One month with a credit allowance for the whole trial (decided 2026-10-13).
    from core.crud.crud_organization import TRIAL_QUOTAS

    assert settings.TRIAL_DAYS == 30
    assert TRIAL_QUOTAS["credits"] == settings.TRIAL_QUOTA_CREDITS
