from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from catalog.app import create_app
from catalog.config import CatalogSettings
from catalog.services.registry import QueryableRegistry
from catalog.store import CatalogStore
from tests.fixtures.gen_catalog import write_catalog, write_nuts


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    write_catalog(tmp_path)
    write_nuts(tmp_path)
    return tmp_path


@pytest.fixture()
def client(catalog_dir: Path) -> Iterator[TestClient]:
    # AUTH defaults to True (see catalog.config.CatalogSettings); tests use
    # the open-access path by default and opt into AUTH=True explicitly
    # (see tests/test_endpoints.py's auth tests) rather than the reverse.
    app = create_app(CatalogSettings(data_dir=catalog_dir, auth=False))
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def store(catalog_dir: Path) -> CatalogStore:
    s = CatalogStore(CatalogSettings(data_dir=catalog_dir))
    s.ensure_current()
    return s


@pytest.fixture()
def registry(store: CatalogStore) -> QueryableRegistry:
    """The queryable registry of the fixture catalog.

    Taken off the store rather than constructed, so these tests exercise the
    registry that was actually derived from the loaded table (a hand-built one
    could advertise columns the fixture doesn't have).
    """
    return store.registry
