"""Custom-domain provisioner abstraction.

The Protocol defines the interface used by the reconciliation helpers
and request handlers; the Fake is for tests and local dev. The real
implementation backed by Caddy on-demand TLS lives in
``caddy_provisioner.py`` — Caddy issues + caches Let's Encrypt certs
on first request, so the runtime cert lifecycle happens outside
``core``'s control plane.
"""

from typing import Protocol


def slugify_domain(base_domain: str) -> str:
    """Convert a hostname to a slugified, dns-safe identifier.

    Example: 'klima.example.com' -> 'cd-klima-example-com'
    """
    return "cd-" + base_domain.lower().replace(".", "-")


class CustomDomainProvisioner(Protocol):
    """Abstraction over custom-domain certificate / routing provisioning."""

    async def provision(self, *, base_domain: str) -> None:
        """Idempotently register the domain with the provisioner."""
        ...

    async def release(self, *, base_domain: str) -> None:
        """Idempotent: missing-domain is treated as success."""
        ...


class FakeProvisioner:
    """Test/local-dev double for CustomDomainProvisioner.

    Records all provision/release calls so tests can assert which domains
    have been registered with the backend.
    """

    def __init__(self) -> None:
        self.created: list[str] = []  # base_domains that have been provisioned

    async def provision(self, *, base_domain: str) -> None:
        if base_domain not in self.created:
            self.created.append(base_domain)

    async def release(self, *, base_domain: str) -> None:
        self.created = [d for d in self.created if d != base_domain]
