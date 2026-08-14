from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.event import Event
from app.events.redis_bus import get_event_bus

class EventReplayService:
    def __init__(self, session: AsyncSession):
        """Event Replay Service re-publishing previously ingested outbox events onto the
        Event Bus, per api_contract.md section 9.A."""
        self.session = session
        self.event_bus = get_event_bus()

    def _to_sql_like(self, pattern: str) -> str:
        """Translate a '*'-wildcard routing_key_pattern (as documented) into a SQL LIKE
        pattern, escaping any literal '%'/'_' already present in the pattern."""
        escaped = pattern.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        return escaped.replace("*", "%")

    async def replay_events(
        self,
        organization_id: UUID,
        routing_key_pattern: Optional[str] = None,
        start_timestamp: Optional[datetime] = None,
        limit: int = 500
    ) -> Dict[str, Any]:
        """Re-publish events matching the given filters, scoped strictly to
        organization_id -- the pattern/timestamp filters narrow WITHIN that boundary, they
        can never widen it to another tenant's events."""
        query = select(Event).where(Event.organization_id == organization_id)
        if start_timestamp:
            query = query.where(Event.created_at >= start_timestamp)
        if routing_key_pattern:
            query = query.where(Event.routing_key.like(self._to_sql_like(routing_key_pattern), escape="\\"))
        query = query.order_by(Event.created_at.asc()).limit(limit)

        res = await self.session.execute(query)
        events = res.scalars().all()

        replayed_count = 0
        for event in events:
            event_data = {
                "id": str(event.id),
                "routing_key": event.routing_key,
                "organization_id": str(event.organization_id),
                "project_id": str(event.project_id) if event.project_id else None,
                "payload": event.payload,
                "replay": True,
            }
            stream_category = event.routing_key.split(":")[0]
            stream_name = f"{stream_category}_stream"
            await self.event_bus.publish(stream_name, event_data)
            replayed_count += 1

        return {"matched_count": len(events), "replayed_count": replayed_count}
