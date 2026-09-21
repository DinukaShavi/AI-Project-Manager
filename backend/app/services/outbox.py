from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.events.redis_bus import get_event_bus

# implementation_roadmap.md Milestone 4 -- Tests: "verify DLQ routing after 5 failures".
MAX_DELIVERY_ATTEMPTS = 5


class OutboxService:
    def __init__(self, session: AsyncSession):
        """Outbox Service processing transactional outbox events atomically."""
        self.session = session
        self.event_bus = get_event_bus()

    async def process_outbox(self, limit: int = 50) -> int:
        """Publish unprocessed outbox events, retrying transient failures and routing
        permanently-failing ones to the Dead Letter Queue (Milestone 4).

        Phase 87 fixed two real defects here:

        1. The commit was previously guarded by `if processed_count > 0`, so when *every*
           event in a batch failed, the `retry_count` increments and `error_log` writes were
           never committed -- they were discarded when the session closed. A poison-pill
           event was therefore retried every second forever with `retry_count` frozen at 0.
        2. Nothing ever routed a failing event to a DLQ, and the poll had no attempt ceiling,
           so a permanently-broken event could never drain out of the queue.
        """
        result = await self.session.execute(
            select(Event)
            .where(
                Event.processed == False,  # noqa: E712 - SQL boolean comparison
                Event.dead_lettered_at.is_(None),  # DLQ'd events are no longer retried
            )
            .order_by(Event.created_at.asc())
            .limit(limit)
        )
        events = result.scalars().all()
        processed_count = 0
        dead_lettered_count = 0

        for event in events:
            try:
                # Prepare event packet
                event_data = {
                    "id": str(event.id),
                    "routing_key": event.routing_key,
                    "organization_id": str(event.organization_id),
                    "project_id": str(event.project_id) if event.project_id else None,
                    "payload": event.payload
                }

                # Publish to broker stream
                # Stream name format: routing_key category (e.g., 'project:created' -> 'project_stream')
                stream_category = event.routing_key.split(":")[0]
                stream_name = f"{stream_category}_stream"

                await self.event_bus.publish(stream_name, event_data)

                # Mark event outbox record as successfully processed
                event.processed = True
                processed_count += 1
            except Exception as e:
                event.retry_count = (event.retry_count or 0) + 1
                event.error_log = str(e)

                # After MAX_DELIVERY_ATTEMPTS the event is considered undeliverable and is
                # routed to the DLQ, where it stops consuming retry cycles and becomes
                # visible to an operator via GET /api/v1/events/dlq.
                if event.retry_count >= MAX_DELIVERY_ATTEMPTS:
                    event.dead_lettered_at = datetime.now(timezone.utc)
                    dead_lettered_count += 1
                    logger.error(
                        f"Outbox: event {event.id} ({event.routing_key}) routed to DLQ after "
                        f"{event.retry_count} failed delivery attempts. Last error: {e}"
                    )

        # Always commit: failures mutate retry_count/error_log/dead_lettered_at, and those
        # writes are exactly what must survive when nothing succeeded.
        if events:
            await self.session.commit()

        if dead_lettered_count:
            logger.warning(f"Outbox: {dead_lettered_count} event(s) routed to the Dead Letter Queue.")

        return processed_count
