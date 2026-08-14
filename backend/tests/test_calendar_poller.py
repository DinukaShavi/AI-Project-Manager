import asyncio
import uuid
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import select
from loguru import logger

import app.db.base # Register models
from app.core.config import settings
from app.core.security import encrypt_token
from app.core.distributed_lock import get_lock_manager
from app.models.tenant import Organization, Workspace
from app.models.project import Project, Meeting
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from app.services.integration import IntegrationService
from app.workers.event_worker import BackgroundEventWorker, CALENDAR_POLLER_LOCK_KEY


def _fake_response(url, json_body):
    return httpx.Response(200, request=httpx.Request("GET", str(url)), json=json_body)


async def _make_org_with_calendar(session, name, token="fake-calendar-access-token", expires_at=None):
    org = Organization(name=name, domain=f"{uuid.uuid4().hex[:8]}.example.com")
    session.add(org)
    await session.flush()

    workspace = Workspace(organization_id=org.id, name=f"{name} Workspace")
    session.add(workspace)
    await session.flush()

    project = Project(organization_id=org.id, workspace_id=workspace.id, name=f"{name} Project")
    session.add(project)
    await session.flush()

    integration = Integration(organization_id=org.id, provider="google_calendar", is_active=True)
    session.add(integration)
    await session.flush()

    oauth_token = OAuthToken(
        organization_id=org.id,
        integration_id=integration.id,
        encrypted_access_token=encrypt_token(token),
        expires_at=expires_at,
    )
    session.add(oauth_token)
    await session.commit()
    return org, project, integration


async def test_calendar_poller_flow():
    print("Initializing Calendar Background Poller validation tests...")

    org_ids = []
    integration_ids = []

    async def fake_events_page1(self, url, **kwargs):
        assert "googleapis.com/calendar/v3/calendars/primary/events" in str(url)
        return _fake_response(url, {"items": [
            {"id": "poll-evt-1", "summary": "Standup", "start": {"dateTime": "2026-08-09T10:00:00Z"}, "end": {"dateTime": "2026-08-09T10:15:00Z"}, "attendees": [{"email": "a@example.com"}]},
        ]})

    async def fake_events_fail(self, url, **kwargs):
        raise httpx.ConnectError("simulated Google Calendar API outage")

    try:
        async with SessionLocal() as session:
            org_a, project_a, integration_a = await _make_org_with_calendar(session, f"Poller Org A {uuid.uuid4().hex[:6]}")
            org_b, project_b, integration_b = await _make_org_with_calendar(session, f"Poller Org B {uuid.uuid4().hex[:6]}")
            # Org C: an INACTIVE integration -- must never be discovered/polled.
            org_c, project_c, integration_c = await _make_org_with_calendar(session, f"Poller Org C {uuid.uuid4().hex[:6]}")
            integration_c.is_active = False
            # Org D: an active integration whose token already expired.
            org_d, project_d, integration_d = await _make_org_with_calendar(
                session, f"Poller Org D {uuid.uuid4().hex[:6]}", expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
            )
            await session.commit()
        org_ids = [org_a.id, org_b.id, org_c.id, org_d.id]
        integration_ids = [integration_a.id, integration_b.id, integration_c.id, integration_d.id]
        print(f"Test orgs created. A={org_a.id} B={org_b.id} C={org_c.id}(inactive) D={org_d.id}(expired token)")

        # 1. Poll interval matches the documented requirement (implementation_roadmap.md
        # Milestone 10: "Poller running every 15 minutes").
        print("\nTest 1: Verifying the poll interval matches the documented 15-minute cadence...")
        assert settings.CALENDAR_POLL_INTERVAL_SECONDS == 900, f"Expected 900s (15 min), got {settings.CALENDAR_POLL_INTERVAL_SECONDS}"
        print("SUCCESS: CALENDAR_POLL_INTERVAL_SECONDS == 900 (15 minutes).")

        # 2. Discovery finds only active google_calendar integrations -- Org C (inactive) must
        # be excluded, Org A/B/D (active) must be included.
        print("\nTest 2: Verifying tenant discovery finds active integrations only...")
        async with SessionLocal() as session:
            discovered = await IntegrationService(session).get_active_calendar_integrations()
        discovered_ids = {i for i, _ in discovered}
        assert integration_a.id in discovered_ids
        assert integration_b.id in discovered_ids
        assert integration_c.id not in discovered_ids, "Inactive integration must not be discovered"
        assert integration_d.id in discovered_ids  # discovery doesn't check expiry -- that's per-sync
        print(f"SUCCESS: Discovered {len(discovered_ids)} active integrations; inactive Org C correctly excluded.")

        # 3. Running the poll sync for an eligible tenant fetches real events and persists
        # them as Meeting rows for that tenant's project, reusing sync_calendar_events().
        print("\nTest 3: Verifying poll sync runs and persists real Meeting rows for Org A...")
        with patch.object(httpx.AsyncClient, "get", new=fake_events_page1):
            async with SessionLocal() as session:
                result_a = await IntegrationService(session).run_calendar_poll_sync(integration_a.id)
        assert result_a[str(project_a.id)] == 1
        async with SessionLocal() as session:
            res = await session.execute(select(Meeting).where(Meeting.project_id == project_a.id))
            meetings = res.scalars().all()
            assert len(meetings) == 1
            assert meetings[0].title == "Standup"
            assert meetings[0].organization_id == org_a.id
        print("SUCCESS: Org A's calendar synced into a real, correctly-scoped Meeting row.")

        # 4. The integration's last_synced_at watermark advances on success (reusing the same
        # watermark column/pattern as the Jira backup-sync poller).
        print("\nTest 4: Verifying the watermark advances after a successful poll...")
        async with SessionLocal() as session:
            refreshed = await session.get(Integration, integration_a.id)
            assert refreshed.last_synced_at is not None
        print("SUCCESS: last_synced_at watermark advanced after successful sync.")

        # 5. Repeated polling of the same events does not create duplicate Meeting rows
        # (idempotency).
        print("\nTest 5: Verifying repeated polling does not create duplicate meetings...")
        with patch.object(httpx.AsyncClient, "get", new=fake_events_page1):
            async with SessionLocal() as session:
                await IntegrationService(session).run_calendar_poll_sync(integration_a.id)
        async with SessionLocal() as session:
            res = await session.execute(select(Meeting).where(Meeting.project_id == project_a.id))
            assert len(res.scalars().all()) == 1, "Expected exactly 1 meeting after re-polling the same event, found duplicates"
        print("SUCCESS: Re-polling the same event updated the existing row instead of duplicating.")

        # 6. A provider/API failure for one tenant is handled safely (no crash, recorded as
        # a failure) and does NOT prevent another, independent tenant from being processed --
        # this mirrors exactly how the worker loop calls run_calendar_poll_sync per-tenant.
        print("\nTest 6: Verifying a provider failure for Org A does not block Org B's independent sync...")
        with patch.object(httpx.AsyncClient, "get", new=fake_events_fail):
            async with SessionLocal() as session:
                result_a_fail = await IntegrationService(session).run_calendar_poll_sync(integration_a.id)
        assert result_a_fail[str(project_a.id)] == -1, "Expected the provider failure to be recorded, not silently dropped or raised"

        with patch.object(httpx.AsyncClient, "get", new=fake_events_page1):
            async with SessionLocal() as session:
                result_b = await IntegrationService(session).run_calendar_poll_sync(integration_b.id)
        assert result_b[str(project_b.id)] == 1, "Org B must sync successfully despite Org A's unrelated provider failure"
        async with SessionLocal() as session:
            res = await session.execute(select(Meeting).where(Meeting.project_id == project_b.id))
            assert len(res.scalars().all()) == 1
        print("SUCCESS: Org A's provider failure was isolated; Org B synced successfully and independently.")

        # 7. An expired OAuth token is detected as a distinct authentication failure
        # (PermissionError), not a generic crash or a silent no-op -- there is no OAuth
        # provider token-refresh mechanism in this codebase to fall back to.
        print("\nTest 7: Verifying an expired Calendar OAuth token raises a distinct auth failure...")
        raised_permission_error = False
        try:
            async with SessionLocal() as session:
                await IntegrationService(session).run_calendar_poll_sync(integration_d.id)
        except PermissionError:
            raised_permission_error = True
        assert raised_permission_error, "Expected PermissionError for an expired OAuth token"
        async with SessionLocal() as session:
            res = await session.execute(select(Meeting).where(Meeting.project_id == project_d.id))
            assert len(res.scalars().all()) == 0, "No meetings should be synced for an expired-token tenant"
            refreshed_d = await session.get(Integration, integration_d.id)
            assert refreshed_d.last_synced_at is None, "Watermark must not advance when the sync never actually ran"
        print("SUCCESS: Expired token correctly raised PermissionError; no data synced, watermark untouched.")

        # 8. Tenant isolation: Org B's meetings must never appear under Org A's project, and
        # vice versa.
        print("\nTest 8: Verifying tenant isolation between Org A's and Org B's meetings...")
        async with SessionLocal() as session:
            res_a = await session.execute(select(Meeting).where(Meeting.project_id == project_a.id))
            res_b = await session.execute(select(Meeting).where(Meeting.project_id == project_b.id))
            ids_a = {m.id for m in res_a.scalars().all()}
            ids_b = {m.id for m in res_b.scalars().all()}
            assert ids_a.isdisjoint(ids_b), "Org A and Org B meetings must never overlap"
        print("SUCCESS: Org A and Org B meeting data remained fully isolated.")

        # 9. The distributed lock (DistributedLockManager, reused rather than a second
        # locking system) actually prevents a concurrent second acquisition of the poller's
        # cycle lock.
        print("\nTest 9: Verifying the distributed lock prevents overlapping poll cycles...")
        lock_manager = get_lock_manager()
        token1 = await lock_manager.acquire_lock(CALENDAR_POLLER_LOCK_KEY, ttl_seconds=5)
        assert token1 is not None
        token2 = await lock_manager.acquire_lock(CALENDAR_POLLER_LOCK_KEY, ttl_seconds=5)
        assert token2 is None, "A second concurrent acquisition of the same poll-cycle lock must fail"
        await lock_manager.release_lock(CALENDAR_POLLER_LOCK_KEY, token1)
        token3 = await lock_manager.acquire_lock(CALENDAR_POLLER_LOCK_KEY, ttl_seconds=5)
        assert token3 is not None, "Lock must be acquirable again after release"
        await lock_manager.release_lock(CALENDAR_POLLER_LOCK_KEY, token3)
        print("SUCCESS: Distributed lock correctly serializes poller cycles across instances.")

        # 10. Run one real cycle of the actual _calendar_poller_loop (not just the service
        # methods it calls) end-to-end: verify structured logging occurs at each documented
        # point, the lock is used, and no access token / secret material ever appears in the
        # logs.
        print("\nTest 10: Running one real _calendar_poller_loop cycle end-to-end, checking logs for leaked secrets...")
        log_lines = []
        sink_id = logger.add(lambda msg: log_lines.append(str(msg)), level="INFO")
        worker = BackgroundEventWorker()
        worker.is_running = True
        with patch.object(httpx.AsyncClient, "get", new=fake_events_page1):
            loop_task = asyncio.create_task(worker._calendar_poller_loop())
            for _ in range(100):
                await asyncio.sleep(0.1)
                if any("Calendar poller: cycle complete." in line for line in log_lines):
                    break
            worker.is_running = False
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
        logger.remove(sink_id)

        full_log = "\n".join(log_lines)
        assert "Calendar poller: cycle starting." in full_log
        assert "discovered" in full_log
        assert "Calendar poller: cycle complete." in full_log
        assert any("skipped" in line and str(org_d.id) in line for line in log_lines), "Expected Org D's expired-token skip to be logged"
        assert "fake-calendar-access-token" not in full_log, "Raw access token leaked into logs"
        assert "fake-google-access-token" not in full_log
        print("SUCCESS: Full poller cycle ran with correct structured logging and no leaked credential material.")

    finally:
        print("\nCleaning up Calendar poller test database entries...")
        async with SessionLocal() as session:
            for oid in org_ids:
                for model in (Meeting,):
                    res = await session.execute(select(model).join(Project, model.project_id == Project.id).where(Project.organization_id == oid))
                    for row in res.scalars().all():
                        await session.delete(row)
                await session.commit()

                tok_res = await session.execute(
                    select(OAuthToken).join(Integration, OAuthToken.integration_id == Integration.id).where(Integration.organization_id == oid)
                )
                for t in tok_res.scalars().all():
                    await session.delete(t)
                await session.commit()

                int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                for i in int_res.scalars().all():
                    await session.delete(i)
                proj_res = await session.execute(select(Project).where(Project.organization_id == oid))
                for p in proj_res.scalars().all():
                    await session.delete(p)
                ws_res = await session.execute(select(Workspace).where(Workspace.organization_id == oid))
                for w in ws_res.scalars().all():
                    await session.delete(w)
                await session.commit()

                org_res = await session.execute(select(Organization).where(Organization.id == oid))
                db_org = org_res.scalar_one_or_none()
                if db_org:
                    await session.delete(db_org)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Calendar Background Poller tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_calendar_poller_flow())
