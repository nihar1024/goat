import pytest
from core.core.config import settings
from core.db.models.credit_rate import CreditRate
from core.db.seed_credit_rates import seed_credit_rates
from sqlalchemy import delete, select
from tests.billing import TERMS, enable_billing


async def _rates(db_session) -> dict[str, CreditRate]:
    db_session.expire_all()
    rows = (await db_session.execute(select(CreditRate))).scalars().all()
    return {row.category: row for row in rows}


@pytest.fixture(autouse=True)
async def empty_table(db_session):
    # The test database is shared by the session: start and leave it empty.
    await db_session.execute(delete(CreditRate))
    await db_session.commit()
    yield
    await db_session.execute(delete(CreditRate))
    await db_session.commit()


@pytest.mark.asyncio
async def test_billing_off_seeds_nothing(db_session):
    await seed_credit_rates(db_session)
    assert await _rates(db_session) == {}


@pytest.mark.asyncio
async def test_billing_on_writes_the_configured_rates(db_session, monkeypatch):
    enable_billing(monkeypatch)
    await seed_credit_rates(db_session)
    rates = await _rates(db_session)
    assert {k: (float(r.rate), r.unit_basis) for k, r in rates.items()} == {
        "compute": (TERMS["CREDIT_RATE_COMPUTE_PER_MINUTE"], "minute"),
        "egress": (TERMS["CREDIT_RATE_EGRESS_PER_GB"], "GB"),
        "ai": (TERMS["CREDIT_RATE_AI_PER_1K_TOKENS"], "1k_tokens"),
    }
    assert {r.source for r in rates.values()} == {"settings"}


@pytest.mark.asyncio
async def test_a_changed_setting_updates_the_row(db_session, monkeypatch):
    enable_billing(monkeypatch)
    await seed_credit_rates(db_session)
    monkeypatch.setattr(settings, "CREDIT_RATE_EGRESS_PER_GB", 35)
    await seed_credit_rates(db_session)
    rates = await _rates(db_session)
    assert float(rates["egress"].rate) == 35
    assert float(rates["compute"].rate) == TERMS["CREDIT_RATE_COMPUTE_PER_MINUTE"]
    assert len(rates) == 3
