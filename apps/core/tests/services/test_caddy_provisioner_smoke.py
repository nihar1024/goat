"""Smoke tests for CaddyProvisioner.

Caddy itself is not exercised — these just verify the provisioner
satisfies the Protocol shape and behaves correctly as a stub.
"""

import pytest
from core.services.caddy_provisioner import CaddyProvisioner


@pytest.mark.asyncio
async def test_provision_is_noop() -> None:
    p = CaddyProvisioner()
    # Should not raise; returns None.
    result = await p.provision(base_domain="klima.example.com")
    assert result is None


@pytest.mark.asyncio
async def test_release_is_noop() -> None:
    p = CaddyProvisioner()
    # Should not raise; should not error even for unknown domain.
    await p.release(base_domain="unknown.example.com")


def test_di_returns_caddy_outside_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check that production DI wires CaddyProvisioner."""
    from core.deps.provisioner import get_provisioner, reset_provisioner

    # We can't actually flip TEST_MODE off in this test environment, so
    # we just verify the import resolves and the class is correct shape.
    # The real DI wiring is exercised manually in dev cluster.
    reset_provisioner()
    monkeypatch.setattr("core.deps.provisioner.settings.TEST_MODE", False)
    p = get_provisioner()
    assert isinstance(p, CaddyProvisioner)
    reset_provisioner()


def test_di_returns_fake_in_test_mode() -> None:
    """In test mode, provisioner stays as FakeProvisioner."""
    from core.core.config import settings
    from core.deps.provisioner import get_provisioner, reset_provisioner
    from core.services.provisioner import FakeProvisioner

    assert settings.TEST_MODE is True
    reset_provisioner()
    p = get_provisioner()
    assert isinstance(p, FakeProvisioner)
    reset_provisioner()
