"""Credit rates from the CREDIT_RATE_* settings (billing only)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.core.config import settings

# The unit each category's rate is per; charge_credits.sql converts the native
# unit (seconds, bytes, tokens) by it.
UNIT_BASIS = {"compute": "minute", "egress": "GB", "ai": "1k_tokens"}


def credit_rates() -> dict[str, float]:
    """The configured credits per unit, by category (empty with billing off)."""
    if not settings.billing_enabled:
        return {}
    rates = {
        "compute": settings.CREDIT_RATE_COMPUTE_PER_MINUTE,
        "egress": settings.CREDIT_RATE_EGRESS_PER_GB,
        "ai": settings.CREDIT_RATE_AI_PER_1K_TOKENS,
    }
    return {category: rate for category, rate in rates.items() if rate is not None}


async def seed_credit_rates(session: AsyncSession) -> None:
    """Write CREDIT_RATE_* to customer.credit_rate, one row per category.

    The operator's settings are the source of truth, so a changed value is
    applied on the next start (past charges keep the rate they were made at,
    credit_usage.rate). Does nothing with billing off. Idempotent."""
    rates = credit_rates()
    if not rates:
        return
    for category, rate in rates.items():
        await session.execute(
            text(
                f"INSERT INTO {settings.SCHEMA}.credit_rate "
                "(category, rate, unit_basis, source) "
                "VALUES (:category, :rate, :unit_basis, 'settings') "
                "ON CONFLICT (category) DO UPDATE SET rate = EXCLUDED.rate, "
                "unit_basis = EXCLUDED.unit_basis, source = EXCLUDED.source, "
                "updated_at = CURRENT_TIMESTAMP "
                f"WHERE ({settings.SCHEMA}.credit_rate.rate, "
                f"{settings.SCHEMA}.credit_rate.unit_basis) "
                "IS DISTINCT FROM (EXCLUDED.rate, EXCLUDED.unit_basis)"
            ),
            {
                "category": category,
                "rate": rate,
                "unit_basis": UNIT_BASIS[category],
            },
        )
    await session.commit()
