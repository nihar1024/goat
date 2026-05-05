"""CustomDomainProvisioner backend for Caddy on-demand TLS.

Caddy handles certificate lifecycle on demand — when a request arrives
for a new hostname, Caddy hits the configured ``ask`` URL (our
``/api/v2/custom-domain-lookup`` endpoint) to decide whether to issue,
then fetches the cert via Let's Encrypt HTTP-01.

There's no per-domain provisioning step for ``core`` to perform —
registration of a domain is just a DB write. This provisioner satisfies
the ``CustomDomainProvisioner`` Protocol with stubs that keep the
existing reconciliation flow happy while Caddy does the real work.
"""


class CaddyProvisioner:
    """CustomDomainProvisioner backed by Caddy on-demand TLS.

    Both methods are no-ops because Caddy handles cert lifecycle outside
    ``core``'s control plane.
    """

    async def provision(self, *, base_domain: str) -> None:
        return None

    async def release(self, *, base_domain: str) -> None:
        # Caddy stops serving the domain once /custom-domain-lookup returns
        # 404. Cached certs expire naturally.
        return None
