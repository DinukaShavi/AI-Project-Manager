import asyncio
from loguru import logger
import app.db.base  # Ensure all models registered before OutboxService resolves mappers
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.outbox import OutboxService
from app.services.integration import IntegrationService
from app.events.redis_bus import get_event_bus
from app.core.distributed_lock import get_lock_manager

CALENDAR_POLLER_LOCK_KEY = "calendar_poller_cycle"

class BackgroundEventWorker:
    def __init__(self):
        """Background Worker managing outbox event dispatch loops, backup-sync polling, and
        stream subscriptions."""
        self.event_bus = get_event_bus()
        self.is_running = False
        self.task = None
        self.backup_sync_task = None
        self.calendar_poller_task = None

    async def start(self) -> None:
        """Connect the Event Bus and launch the background polling loops."""
        self.is_running = True
        await self.event_bus.connect()

        # Start the outbox poller loop as an asynchronous background task
        self.task = asyncio.create_task(self._outbox_loop())
        # Start the Jira backup delta-sync loop (per system_architecture_design.md's Sync
        # frequency matrix), the documented backup-cron counterpart to webhook ingestion.
        self.backup_sync_task = asyncio.create_task(self._jira_backup_sync_loop())
        # Start the Calendar poller (implementation_roadmap.md Milestone 10: "Poller running
        # every 15 minutes fetching updated meetings" -- Calendar's only real sync path,
        # since it's documented as polling-driven rather than webhook-driven).
        self.calendar_poller_task = asyncio.create_task(self._calendar_poller_loop())
        logger.info("Background event worker, Outbox publisher, Jira backup-sync poller, and Calendar poller started.")

    async def stop(self) -> None:
        """Cancel background loops and disconnect the Event Bus broker connection."""
        self.is_running = False
        for task in (self.task, self.backup_sync_task, self.calendar_poller_task):
            if task:
                task.cancel()
                try:
                    await task
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

    async def _jira_backup_sync_loop(self) -> None:
        """Periodic backup delta-sync poll across every active Jira integration, run every
        settings.JIRA_BACKUP_SYNC_INTERVAL_SECONDS (default 4h, per docs)."""
        while self.is_running:
            try:
                async with SessionLocal() as session:
                    integration_service = IntegrationService(session)
                    results = await integration_service.run_backup_sync_all()
                    total = sum(c for c in results.values() if c > 0)
                    if results:
                        logger.info(f"Jira backup-sync poll ingested {total} events across {len(results)} integration(s).")
            except Exception as e:
                logger.error(f"Error in Jira backup-sync poll loop: {e}")
            await asyncio.sleep(settings.JIRA_BACKUP_SYNC_INTERVAL_SECONDS)

    async def _calendar_poller_loop(self) -> None:
        """Periodic Google Calendar sync poll across every active Calendar integration, every
        settings.CALENDAR_POLL_INTERVAL_SECONDS (default 15 min, per
        implementation_roadmap.md Milestone 10). Reuses
        IntegrationService.sync_calendar_events() -- the exact same logic the manual
        POST /calendar/sync endpoint uses -- via run_calendar_poll_sync(), so both paths stay
        behaviorally identical. Distributed-locked (DistributedLockManager, the same
        Redis-backed Redlock manager used elsewhere in this codebase) so that if this app is
        horizontally scaled, only one instance runs a given poll cycle -- otherwise multiple
        processes would each independently poll and double-write the same tenants' meetings.
        """
        lock_manager = get_lock_manager()
        while self.is_running:
            lock_token = await lock_manager.acquire_lock(CALENDAR_POLLER_LOCK_KEY, ttl_seconds=300)
            if not lock_token:
                logger.info("Calendar poller: cycle skipped, another instance already holds the poll lock.")
            else:
                try:
                    logger.info("Calendar poller: cycle starting.")
                    async with SessionLocal() as discovery_session:
                        integrations = await IntegrationService(discovery_session).get_active_calendar_integrations()
                    logger.info(f"Calendar poller: discovered {len(integrations)} active Google Calendar integration(s).")

                    for integration_id, organization_id in integrations:
                        logger.info(f"Calendar poller: starting sync for organization {organization_id} (integration {integration_id}).")
                        try:
                            async with SessionLocal() as tenant_session:
                                result = await IntegrationService(tenant_session).run_calendar_poll_sync(integration_id)
                            logger.info(f"Calendar poller: organization {organization_id} synced successfully -- {result}.")
                        except PermissionError:
                            logger.warning(f"Calendar poller: organization {organization_id} skipped -- Calendar OAuth token expired, re-authorization required.")
                        except Exception as e:
                            logger.error(f"Calendar poller: sync failed for organization {organization_id} -- {e}")

                    logger.info("Calendar poller: cycle complete.")
                except Exception as e:
                    logger.error(f"Error in Calendar poller cycle: {e}")
                finally:
                    await lock_manager.release_lock(CALENDAR_POLLER_LOCK_KEY, lock_token)
            await asyncio.sleep(settings.CALENDAR_POLL_INTERVAL_SECONDS)


# Singleton background worker instance
event_worker = BackgroundEventWorker()
