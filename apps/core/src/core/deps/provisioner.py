"""Dependency-injection helpers for the white-label custom domains feature.

The ``CustomDomainProvisioner`` Protocol abstracts the per-domain
provisioning backend; ``FakeProvisioner`` is used in tests/dev and
``CaddyProvisioner`` is used in any non-test environment. This module
wires the singleton provisioner used by the request handlers.
"""

from core.core.config import settings
from core.services.provisioner import CustomDomainProvisioner, FakeProvisioner

_provisioner_singleton: CustomDomainProvisioner | None = None


def get_provisioner() -> CustomDomainProvisioner:
    """Return the configured CustomDomainProvisioner.

    In test mode (``settings.TEST_MODE``) we use ``FakeProvisioner``.
    Otherwise we use ``CaddyProvisioner`` — Caddy itself runs as a
    separate Deployment and handles cert lifecycle on demand. Lazy
    import keeps this module loadable in environments where the
    Caddy backend is not used.
    """
    global _provisioner_singleton
    if _provisioner_singleton is None:
        if settings.TEST_MODE:
            _provisioner_singleton = FakeProvisioner()
        else:
            from core.services.caddy_provisioner import CaddyProvisioner

            _provisioner_singleton = CaddyProvisioner()
    return _provisioner_singleton


def set_provisioner(p: CustomDomainProvisioner) -> None:
    """Install a specific provisioner (test fixture / dev override)."""
    global _provisioner_singleton
    _provisioner_singleton = p


def reset_provisioner() -> None:
    """Tear down the singleton -- used between tests."""
    global _provisioner_singleton
    _provisioner_singleton = None
