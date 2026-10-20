"""Billing switched on for a test: the switch, the webhook secret and the
operator's trial and credit-rate terms (core has no defaults for them)."""

import pytest
from core.core.config import settings

WEBHOOK_SECRET = "shh"

# Arbitrary values; tests that care read them back from `settings`.
TERMS = {
    "TRIAL_DAYS": 14,
    "TRIAL_QUOTA_STORAGE_MB": 1000,
    "TRIAL_QUOTA_PROJECTS": 20,
    "TRIAL_QUOTA_EDITORS": 3,
    "TRIAL_QUOTA_VIEWERS": 4,
    "TRIAL_QUOTA_CREDITS": 500,
    "CREDIT_RATE_COMPUTE_PER_MINUTE": 10,
    "CREDIT_RATE_EGRESS_PER_GB": 20,
    "CREDIT_RATE_AI_PER_1K_TOKENS": 1,
}


def enable_billing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BILLING_ENABLED", True)
    monkeypatch.setattr(settings, "BILLING_WEBHOOK_SECRET", WEBHOOK_SECRET)
    for name, value in TERMS.items():
        monkeypatch.setattr(settings, name, value)


def enable_accounts_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Billing plus the Odoo connection and the accounts bridge's key."""
    enable_billing(monkeypatch)
    monkeypatch.setattr(settings, "ODOO_URL", "https://odoo.test")
    monkeypatch.setattr(settings, "ODOO_DB", "test")
    monkeypatch.setattr(settings, "ODOO_ACCOUNTS_API_KEY", "key")
