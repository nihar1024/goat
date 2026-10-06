"""These tests talk to the staging Odoo only: no database, no app.

The root conftest has two autouse fixtures that build a Postgres test schema
for the whole session; override them with no-ops so this directory never needs
a database (and keeps working when none is running).
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def session_fixture() -> None:
    return None


@pytest.fixture(autouse=True)
def session_override() -> None:
    return None
