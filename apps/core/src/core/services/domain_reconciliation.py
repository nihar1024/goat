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


async def _resolve(domain: str, rdtype: str) -> list[str]:
    """Resolve records of ``rdtype`` for ``domain``.

    Returns string-form values (CNAME targets lowercased with trailing dot
    preserved; A/AAAA addresses normalized to canonical form). An empty
    list means NXDOMAIN or NoAnswer. Raises RuntimeError for any other DNS
    error so callers can surface it transiently without flipping state to
    FAILED.
    """
    try:
        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = 5  # seconds total budget for the lookup
        answer = await resolver.resolve(domain, rdtype)
        if rdtype == "CNAME":
            return [str(rdata.target).lower() for rdata in answer]
        return [str(rdata).strip() for rdata in answer]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as exc:
        raise RuntimeError(f"DNS error: {exc}") from exc


def _canonical_matches(targets: list[str], canonical_target: str) -> bool:
    """True if any resolved CNAME target matches the canonical target.

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
    """Verify a custom domain points at the GOAT cluster.

    Two valid configurations:

    * Subdomain: customer's hostname has a CNAME pointing at ``canonical_target``.
    * Apex: customer's hostname has an A/AAAA matching the IPs that
      ``canonical_target`` itself resolves to. CNAMEs are not allowed at a
      zone apex (RFC 1034), so apex customers must use A/AAAA directly.

    Returns ``(VERIFIED, None)`` on match. Returns ``(PENDING, message)``
    otherwise -- message describes what was found, suitable for showing to
    the admin in the UI.
    """
    # 1) CNAME path (covers all subdomain cases). Cheapest check, do first.
    try:
        cnames = await _resolve(base_domain, "CNAME")
    except RuntimeError as exc:
        return DnsStatus.PENDING, str(exc)

    if cnames and _canonical_matches(cnames, canonical_target):
        return DnsStatus.VERIFIED, None

    # 2) A path (apex case, or a customer who pinned A directly even for a
    # subdomain). We resolve the canonical target ourselves to get the
    # current LB IP — that way changing the LB only requires updating the
    # canonical target's A record; both CNAME and apex customers
    # automatically follow. AAAA is intentionally skipped: we don't ask
    # customers to set IPv6 in the UI, so checking it would just create
    # confusing edge cases.
    try:
        expected_ips = set(await _resolve(canonical_target, "A"))
    except RuntimeError as exc:
        return DnsStatus.PENDING, str(exc)

    if not expected_ips:
        return (
            DnsStatus.PENDING,
            f"Could not resolve canonical target {canonical_target}",
        )

    try:
        customer_ips = set(await _resolve(base_domain, "A"))
    except RuntimeError as exc:
        return DnsStatus.PENDING, str(exc)

    if customer_ips & expected_ips:
        return DnsStatus.VERIFIED, None

    # Nothing matched — explain what we saw, prioritizing the most useful hint.
    if cnames:
        return (
            DnsStatus.PENDING,
            f"CNAME points to {cnames[0]} (expected {canonical_target})",
        )
    if customer_ips:
        return (
            DnsStatus.PENDING,
            (
                f"A points to {sorted(customer_ips)[0]} "
                f"(expected {sorted(expected_ips)[0]})"
            ),
        )
    return (
        DnsStatus.PENDING,
        f"No CNAME or A record found for {base_domain}",
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
