import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import User
from app.models.event import Event
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


@router.get("/dlq", status_code=status.HTTP_200_OK)
async def list_dead_letter_queue(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Dead Letter Queue admin view, per implementation_roadmap.md Milestone 4
    (`GET /api/v1/events/dlq`, "Admin view").

    Lists events that exhausted `MAX_DELIVERY_ATTEMPTS` publish attempts and were routed out
    of the retry loop, together with the last error that caused each failure. OrgAdmin/
    SuperAdmin only, and always scoped to the caller's own organization."""
    role_names = {r.name for r in current_user.roles}
    if not role_names & ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OrgAdmin or SuperAdmin roles may view the Dead Letter Queue."
        )

    res = await db.execute(
        select(Event)
        .where(
            Event.organization_id == current_user.organization_id,
            Event.dead_lettered_at.is_not(None),
        )
        .order_by(Event.dead_lettered_at.desc())
        .limit(min(max(limit, 1), 500))
    )
    events = res.scalars().all()

    return {
        "dead_letter_count": len(events),
        "events": [
            {
                "id": str(e.id),
                "routing_key": e.routing_key,
                "project_id": str(e.project_id) if e.project_id else None,
                "retry_count": e.retry_count,
                "error_log": e.error_log,
                "dead_lettered_at": e.dead_lettered_at,
                "created_at": e.created_at,
            }
            for e in events
        ]
    }


@router.post("/dlq/{event_id}/requeue", status_code=status.HTTP_200_OK)
async def requeue_dead_letter_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Return a dead-lettered event to the outbox for another delivery attempt, once the
    underlying cause has been fixed. Without this a DLQ is a one-way trip, so Milestone 4's
    retry pipeline could never actually recover. OrgAdmin/SuperAdmin only, tenant-scoped."""
    role_names = {r.name for r in current_user.roles}
    if not role_names & ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OrgAdmin or SuperAdmin roles may requeue dead-lettered events."
        )

    res = await db.execute(
        select(Event).where(
            Event.id == event_id,
            Event.organization_id == current_user.organization_id,
        )
    )
    event = res.scalar_one_or_none()
    # Another organization's event is indistinguishable from a nonexistent one.
    if event is None or event.dead_lettered_at is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dead-lettered event not found."
        )

    event.dead_lettered_at = None
    event.retry_count = 0
    event.error_log = None

    await AuditService(db).log(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="events:dlq_requeue",
        details={"event_id": str(event_id), "routing_key": event.routing_key},
    )
    await db.commit()

    return {"status": "requeued", "event_id": str(event_id)}
