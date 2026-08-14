from typing import List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification import Notification

class NotificationService:
    def __init__(self, session: AsyncSession):
        """Notification Service managing per-user alert delivery state."""
        self.session = session

    async def mark_notifications_read(
        self,
        notification_ids: List[UUID],
        user_id: UUID,
        organization_id: UUID
    ) -> int:
        """Mark the given notifications as read, scoped to the caller's own user_id and
        organization_id. Notifications are personal (not merely org-shared) -- a user must
        only be able to mark their own notifications as read, never a colleague's or another
        organization's, even if the ID is known/guessed."""
        if not notification_ids:
            return 0

        res = await self.session.execute(
            select(Notification).where(
                Notification.id.in_(notification_ids),
                Notification.user_id == user_id,
                Notification.organization_id == organization_id,
            )
        )
        rows = res.scalars().all()
        for notification in rows:
            notification.is_read = True
        await self.session.commit()
        return len(rows)
