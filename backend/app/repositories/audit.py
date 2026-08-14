from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import BaseRepository
from app.models.audit import AuditLog
from app.models.tenant import User

class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(AuditLog, session)

    async def list_filtered(
        self,
        organization_id: UUID,
        limit: int = 50,
        offset: int = 0,
        action: Optional[str] = None,
        user_email: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[List[Tuple[AuditLog, Optional[str]]], int]:
        """Fetch a page of audit_logs for an organization, newest first, joined with the
        acting user's email for display. Returns (rows, total_matching_count)."""
        base_query = select(AuditLog, User.email).outerjoin(User, AuditLog.user_id == User.id).where(
            AuditLog.organization_id == organization_id
        )

        if action:
            base_query = base_query.where(AuditLog.action == action)
        if user_email:
            base_query = base_query.where(User.email == user_email)
        if start_date:
            base_query = base_query.where(AuditLog.created_at >= start_date)
        if end_date:
            base_query = base_query.where(AuditLog.created_at <= end_date)

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        page_query = base_query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(page_query)).all()

        return [(row[0], row[1]) for row in rows], total
