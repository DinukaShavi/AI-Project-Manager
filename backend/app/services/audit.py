from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog
from app.repositories.audit import AuditLogRepository

class AuditService:
    def __init__(self, session: AsyncSession):
        """Audit Service persisting and querying append-only audit trail entries for
        security-relevant actions."""
        self.session = session
        self.repository = AuditLogRepository(session)

    async def log(
        self,
        organization_id: UUID,
        action: str,
        user_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """Persist an audit_logs entry. Caller is responsible for committing (or letting an
        already-committed surrounding transaction cover it), matching the rest of the codebase's
        service-layer pattern of not committing inside nested helper calls unless it owns the unit
        of work."""
        entry = AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            details=details or {},
            ip_address=ip_address
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_logs(
        self,
        organization_id: UUID,
        limit: int = 50,
        offset: int = 0,
        action: Optional[str] = None,
        user_email: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[List[Tuple[AuditLog, Optional[str]]], int]:
        """List a paginated, filtered page of this organization's audit trail, newest first."""
        return await self.repository.list_filtered(
            organization_id=organization_id,
            limit=limit,
            offset=offset,
            action=action,
            user_email=user_email,
            start_date=start_date,
            end_date=end_date
        )
