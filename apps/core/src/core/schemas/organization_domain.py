"""Pydantic schemas for the OrganizationDomain resource.

Phase 2 of the white-label custom domains feature. These schemas define
the request/response shapes used by Phase 4 endpoints and the
reconciliation handlers introduced in Phase 3.
"""

import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.db.models.organization_domain import (
    CertStatus,
    DnsStatus,
    DomainKind,
)

# RFC 1035 hostname: labels of [a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?, dot-separated.
HOSTNAME_REGEX = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)

# Hostnames a customer cannot register (would conflict with first-party services).
RESERVED_HOSTNAME_SUFFIXES = ("plan4better.de",)


class OrganizationDomainCreate(BaseModel):
    """Body of POST /organizations/{org_id}/domains/."""

    base_domain: str = Field(..., max_length=253)

    @field_validator("base_domain")
    @classmethod
    def _validate_hostname(cls, v: str) -> str:
        v = v.strip().lower()
        if not HOSTNAME_REGEX.match(v):
            raise ValueError("Invalid hostname format")
        labels = v.split(".")
        if len(labels) < 3:
            # Reject apex (e.g. 'ministry.de'). v1 supports only subdomains
            # like 'klima.ministry.de' — apex needs ALIAS/ANAME records and is
            # planned for a later milestone.
            raise ValueError("Apex domains are not supported in v1; use a subdomain")
        if labels[0] == "www":
            raise ValueError("Subdomain cannot be 'www'")
        for suffix in RESERVED_HOSTNAME_SUFFIXES:
            if v == suffix or v.endswith("." + suffix):
                raise ValueError(f"Hostname {v} is reserved")
        return v


class OrganizationDomainUpdate(BaseModel):
    """Internal: used by reconciliation handlers to update status fields."""

    dns_status: Optional[DnsStatus] = None
    dns_status_message: Optional[str] = None
    dns_last_checked_at: Optional[datetime] = None
    cert_status: Optional[CertStatus] = None
    cert_status_message: Optional[str] = None


class OrganizationDomainRead(BaseModel):
    """Response of GET /organizations/{org_id}/domains/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    base_domain: str
    kind: DomainKind
    dns_status: DnsStatus
    dns_status_message: Optional[str]
    dns_last_checked_at: Optional[datetime]
    cert_status: CertStatus
    cert_status_message: Optional[str]
    created_at: datetime
    # Populated via LEFT JOIN against project_public + project so the
    # White Label list can show "Assigned to" without an N+1 client query.
    # Null when no published project currently uses this domain.
    assigned_project_id: Optional[UUID] = None
    assigned_project_name: Optional[str] = None
