"""Billing switched on for a test: Odoo connection plus the webhook secret."""

import pytest
from core.core.config import settings

WEBHOOK_SECRET = "shh"


def enable_billing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ODOO_URL", "https://odoo.test")
    monkeypatch.setattr(settings, "ODOO_DB", "test")
    monkeypatch.setattr(settings, "ODOO_WEBHOOK_SECRET", WEBHOOK_SECRET)
