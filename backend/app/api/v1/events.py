import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import User
from app.core.rbac_pdp import ADMIN_ROLES
from app.services.event_replay import EventReplayService
from app.services.audit import AuditService

router = APIRouter()

class ReplayEventsRequest(BaseModel):
    routing_key_pattern: Optional[str] = Field(None, description="'*'-wildcard pattern over routing_key, e.g. 'github:*'")
    start_timestamp: Optional[datetime] = Field(None, description="Only replay events created at or after this timestamp")

@router.post("/replay", status_code=status.HTTP_202_ACCEPTED)
async def replay_events(
    payload: ReplayEventsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Replay previously ingested events, per api_contract.md section 9.A. OrgAdmin/
    SuperAdmin only. Always scoped to the authenticated user's own organization --
    routing_key_pattern/start_timestamp only narrow within that boundary."""
    role_names = {r.name for r in current_user.roles}
    if not role_names & ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OrgAdmin or SuperAdmin roles may replay events."
        )

    service = EventReplayService(db)
    result = await service.replay_events(
        organization_id=current_user.organization_id,
        routing_key_pattern=payload.routing_key_pattern,
        start_timestamp=payload.start_timestamp
    )

    replay_id = str(uuid.uuid4())
    await AuditService(db).log(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="events:replay",
        details={
            "replay_id": replay_id,
            "routing_key_pattern": payload.routing_key_pattern,
            "matched_count": result["matched_count"],
            "replayed_count": result["replayed_count"],
        }
    )
    await db.commit()

    return {
        "status": "accepted",
        "replay_id": replay_id,
        "matched_count": result["matched_count"],
        "replayed_count": result["replayed_count"],
    }
