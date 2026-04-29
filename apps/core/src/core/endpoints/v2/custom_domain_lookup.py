"""Anonymous endpoint that resolves an incoming Host header to a project ID.

Called by the Next.js middleware on every request to a non-canonical host.
Must NOT require authentication and must be cheap to call (single indexed
JOIN). Returns 404 when the host is unknown, inactive, or not assigned to
a published project.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from core.db.models.organization_domain import (
    CertStatus,
    OrganizationDomain,
)
from core.db.models.project import ProjectPublic
from core.db.session import AsyncSession
from core.endpoints.deps import get_db

router = APIRouter()


@router.get(
    "/custom-domain-lookup",
    summary="Resolve a custom domain hostname to a published project ID",
)
async def custom_domain_lookup(
    host: str = Query(..., max_length=253),
    async_session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Anonymous: returns ``{project_id}`` for an active assigned host, else 404.

    Used by the Next.js middleware on every request that arrives with a
    non-canonical Host header.
    """
    host = host.strip().lower()

    result = await async_session.execute(
        select(ProjectPublic.project_id)
        .join(
            OrganizationDomain,
            OrganizationDomain.id == ProjectPublic.custom_domain_id,
        )
        .where(
            OrganizationDomain.base_domain == host,
            OrganizationDomain.cert_status == CertStatus.ACTIVE,
        )
    )
    project_id = result.scalar_one_or_none()
    if project_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no project assigned to this host",
        )
    return {"project_id": str(project_id)}
