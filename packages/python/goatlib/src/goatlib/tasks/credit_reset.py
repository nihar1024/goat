"""credit_reset: the monthly credit period of subscribed organizations.

An organization with a subscription gets its credits every month, whatever the
subscription's term (a yearly contract too): when credits_reset_at has passed,
used_credits goes back to 0 and credits_reset_at moves on by whole months.
Core sets the first date when a subscription arrives from Odoo.

Trials are left alone: a trial's credits last the whole trial, and its end
(plan_renewal_date) belongs to trial_expiry. Organizations without a reset date
(self-hosted, trials) are never touched. Off with billing off."""

from __future__ import annotations

import calendar
import logging
from datetime import datetime

from pydantic import BaseModel, Field

from goatlib.tasks._db import core_dsn, customer_schema

logger = logging.getLogger(__name__)


class CreditResetParams(BaseModel):
    dry_run: bool = Field(default=False)


def should_reset(credits_reset_at: datetime | None, now: datetime) -> bool:
    return credits_reset_at is not None and credits_reset_at <= now


def _add_month(d: datetime) -> datetime:
    month = d.month + 1
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def advance_renewal(current: datetime, now: datetime) -> datetime:
    """The first monthly boundary after now, counted from current."""
    d = current
    while d <= now:
        d = _add_month(d)
    return d


DUE_SQL = (
    "SELECT id, credits_reset_at FROM {schema}.organization "
    "WHERE credits_reset_at IS NOT NULL AND credits_reset_at <= $1 "
    "AND on_trial IS NOT TRUE"
)


async def main(params: CreditResetParams = CreditResetParams()) -> dict:
    """Windmill entry point: start a new credit month where one is due."""
    from goatlib.tasks._db import SKIPPED, billing_enabled

    if not billing_enabled():
        return SKIPPED
    import asyncpg

    schema = customer_schema()
    now = datetime.utcnow()
    core = await asyncpg.connect(dsn=core_dsn(), timeout=10)
    reset = 0
    try:
        rows = await core.fetch(DUE_SQL.format(schema=schema), now)
        for r in rows:
            if params.dry_run:
                reset += 1
                continue
            await core.execute(
                f"UPDATE {schema}.organization "
                f"SET used_credits = 0, credits_reset_at = $2 WHERE id = $1",
                r["id"],
                advance_renewal(r["credits_reset_at"], now),
            )
            reset += 1
    finally:
        await core.close()
    summary = {"reset": reset}
    logger.info("credit_reset: %s", summary)
    return summary
