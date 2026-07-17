from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.event import Event
from app.events.redis_bus import get_event_bus

class OutboxService:
    def __init__(self, session: AsyncSession):
        """Outbox Service processing transactional outbox events atomically."""
        self.session = session
        self.event_bus = get_event_bus()

    async def process_outbox(self, limit: int = 50) -> int:
        """Fetch unprocessed outbox events, publish them, and flag as processed."""
        result = await self.session.execute(
            select(Event)
            .where(Event.processed == False)
            .order_by(Event.created_at.asc())
            .limit(limit)
        )
        events = result.scalars().all()
        processed_count = 0
        
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
                # Log errors and increment retry count to prevent blockages
                event.retry_count += 1
                event.error_log = str(e)
                
        if processed_count > 0:
            await self.session.commit()
            
        return processed_count
