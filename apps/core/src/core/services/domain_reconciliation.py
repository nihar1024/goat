"""Reconciliation helpers shared by sync endpoints and the periodic CronJob.

These helpers translate between the database state machine
(DnsStatus / CertStatus) and the world (DNS resolution, custom-domain
provisioner). They are pure async functions so they can be unit-tested
without a database, provisioner backend, or HTTP server.
"""

from typing import Optional

import dns.asyncresolver
import dns.exception
import dns.resolver
from core.db.models.organization_domain import (
    DnsStatus,
    OrganizationDomain,
)
from core.services.provisioner import CustomDomainProvisioner


async def _resolve_cname(domain: str) -> list[str]:
    """Resolve CNAME records for ``domain``.

    Returns lowercased target hostnames as they came back from dnspython
    (trailing dot preserved). An empty list means NXDOMAIN or NoAnswer.
    Raises RuntimeError for any other DNS error so callers can surface it
    transiently without flipping state to FAILED.
    """
    try:
        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = 5  # seconds total budget for the lookup
        answer = await resolver.resolve(domain, "CNAME")
        return [str(rdata.target).lower() for rdata in answer]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as exc:
        raise RuntimeError(f"DNS error: {exc}") from exc


def _canonical_matches(targets: list[str], canonical_target: str) -> bool:
    """True if any resolved target matches the canonical target.

    Both sides are normalized (lowercased, trailing dot stripped) before
    comparison.
    """
    canon = canonical_target.lower().rstrip(".")
    return any(t.rstrip(".") == canon for t in targets)


async def check_dns(
    base_domain: str,
    *,
    canonical_target: str,
) -> tuple[DnsStatus, Optional[str]]:
    """Verify a custom domain's CNAME points at the GOAT cluster.

    Returns ``(VERIFIED, None)`` on match. Returns ``(PENDING, message)``
    when DNS is not yet configured correctly -- message describes what was
    found, suitable for showing to the admin in the UI.
    """
    try:
        targets = await _resolve_cname(base_domain)
    except RuntimeError as exc:
        return DnsStatus.PENDING, str(exc)

    if not targets:
        return DnsStatus.PENDING, f"No CNAME record found for {base_domain}"

    if _canonical_matches(targets, canonical_target):
        return DnsStatus.VERIFIED, None

    return (
        DnsStatus.PENDING,
        f"CNAME points to {targets[0]} (expected {canonical_target})",
    )


async def provision_domain(
    domain: OrganizationDomain,
    *,
    provisioner: CustomDomainProvisioner,
) -> None:
    """Tell the provisioner about a newly verified domain.

    For Caddy this is a no-op; cert issuance happens lazily on first
    request. The helper indirection is kept as a wiring point for any
    pre/post logic (audit logging, cache warming, etc.).
    """
    await provisioner.provision(base_domain=domain.base_domain)


async def release_domain(
    domain: OrganizationDomain,
    *,
    provisioner: CustomDomainProvisioner,
) -> None:
    """Release the domain from the provisioner. Idempotent."""
    await provisioner.release(base_domain=domain.base_domain)
