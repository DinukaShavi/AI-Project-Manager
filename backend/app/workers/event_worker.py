import asyncio
from loguru import logger
import app.db.base  # Ensure all models registered before OutboxService resolves mappers
from app.db.session import SessionLocal
from app.services.outbox import OutboxService
from app.events.redis_bus import get_event_bus

class BackgroundEventWorker:
    def __init__(self):
        """Background Worker managing outbox event dispatch loops and stream subscriptions."""
        self.event_bus = get_event_bus()
        self.is_running = False
        self.task = None

    async def start(self) -> None:
        """Connect the Event Bus and launch the background polling loops."""
        self.is_running = True
        await self.event_bus.connect()
        
        # Start the outbox poller loop as an asynchronous background task
        self.task = asyncio.create_task(self._outbox_loop())
        logger.info("Background event worker and Outbox publisher started.")

    async def stop(self) -> None:
        """Cancel background loops and disconnect the Event Bus broker connection."""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.event_bus.disconnect()
        logger.info("Background event worker stopped cleanly.")

    async def _outbox_loop(self) -> None:
        """Continuous polling loop dispatching events from database Outbox table."""
        while self.is_running:
            try:
                # Obtain a fresh database session for outbox polling
                async with SessionLocal() as session:
                    outbox = OutboxService(session)
                    count = await outbox.process_outbox()
                    if count > 0:
                        logger.info(f"Outbox publisher processed {count} events.")
            except Exception as e:
                logger.error(f"Error in background outbox dispatch loop: {e}")
            # Check for new outbox events every 1 second
            await asyncio.sleep(1)


# Singleton background worker instance
event_worker = BackgroundEventWorker()
