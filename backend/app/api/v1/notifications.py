from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import User
from app.services.notification import NotificationService

router = APIRouter()

class MarkNotificationsReadRequest(BaseModel):
    notification_ids: List[UUID] = Field(..., description="Notification IDs to mark as read")

@router.put("/read", status_code=status.HTTP_200_OK)
async def mark_notifications_read(
    payload: MarkNotificationsReadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark notifications as read, per api_contract.md section 16.A. Scoped to the
    authenticated user's own notifications only -- IDs belonging to another user or
    organization are silently ignored (not updated), never leaked or errored on."""
    service = NotificationService(db)
    updated_count = await service.mark_notifications_read(
        notification_ids=payload.notification_ids,
        user_id=current_user.id,
        organization_id=current_user.organization_id
    )
    return {
        "status": "success",
        "requested_count": len(payload.notification_ids),
        "updated_count": updated_count
    }
