from datetime import datetime

from goatlib.tasks.credit_reset import advance_renewal, should_reset


def test_should_reset():
    now = datetime(2026, 7, 1, 0, 5)
    assert should_reset(datetime(2026, 7, 1, 0, 0), now) is True
    assert should_reset(datetime(2026, 8, 1, 0, 0), now) is False
    assert should_reset(None, now) is False


def test_advance_renewal_jumps_past_now_in_month_steps():
    # renewal far in the past -> advance month-by-month to first boundary after now
    now = datetime(2026, 7, 15)
    out = advance_renewal(datetime(2026, 1, 31), now)
    assert out > now
    # day clamps for short months along the way; result is a real date after now
    assert out.year == 2026 and out.month in (7, 8)  # next boundary after Jul 15


def test_billing_tasks_do_nothing_with_billing_off(monkeypatch):
    # Self-hosted workers: no metering, no trials, no Odoo pushes.
    import asyncio

    from goatlib.tasks import (
        compute_rollup,
        credit_reset,
        odoo_entitlement,
        traffic_rollup,
        trial_expiry,
    )
    from goatlib.tasks._db import SKIPPED

    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    for task in (compute_rollup, traffic_rollup, credit_reset):
        assert asyncio.run(task.main()) == SKIPPED
    for task in (trial_expiry, odoo_entitlement):
        assert task.main() == SKIPPED
