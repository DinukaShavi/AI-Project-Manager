from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import User
from app.services.audit import AuditService
from app.core.rbac_pdp import ADMIN_ROLES

router = APIRouter()


@router.get("", status_code=status.HTTP_200_OK)
async def list_audit_logs(
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    user_email: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List the authenticated user's organization audit trail (read-only), paginated and
    filterable by action, acting user's email, and date range. Restricted to OrgAdmin/SuperAdmin."""
    role_names = {r.name for r in current_user.roles}
    if not role_names & ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OrgAdmin or SuperAdmin roles may view the audit log."
        )

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    service = AuditService(db)
    rows, total = await service.list_logs(
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
        action=action,
        user_email=user_email,
        start_date=start_date,
        end_date=end_date
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": [
            {
                "id": str(log.id),
                "timestamp": log.created_at,
                "user_id": str(log.user_id) if log.user_id else None,
                "user_email": email,
                "action": log.action,
                "details": log.details,
                "ip_address": log.ip_address
            }
            for log, email in rows
        ]
    }
