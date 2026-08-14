import asyncio
import uuid
import httpx
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.core.security import encrypt_token
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project, Meeting
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


def _fake_response(url, json_body):
    return httpx.Response(200, request=httpx.Request("GET", str(url)), json=json_body)


async def test_calendar_sync_flow():
    print("Initializing Google Calendar Sync validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    org_c_id = None
    project_a_id = None
    project_c_id = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Cal Sync Org A {suffix}", domain=f"calsync-a-{suffix}.com")
                org_b = Organization(name=f"Cal Sync Org B {suffix}", domain=f"calsync-b-{suffix}.com")
                org_c = Organization(name=f"Cal Sync Org C {suffix}", domain=f"calsync-c-{suffix}.com")
                session.add_all([org_a, org_b, org_c])
                await session.flush()
                org_a_id, org_b_id, org_c_id = org_a.id, org_b.id, org_c.id

                workspace_a = Workspace(organization_id=org_a_id, name="Cal Sync Workspace A")
                workspace_c = Workspace(organization_id=org_c_id, name="Cal Sync Workspace C")
                session.add_all([workspace_a, workspace_c])
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Cal Sync Project A")
                project_c = Project(organization_id=org_c_id, workspace_id=workspace_c.id, name="Cal Sync Project C (no calendar connected)")
                session.add_all([project_a, project_c])
                await session.flush()
                project_a_id = project_a.id
                project_c_id = project_c.id

                # Org A has an active Google Calendar OAuth connection; Org C deliberately does not.
                integration_a = Integration(organization_id=org_a_id, provider="google_calendar", is_active=True)
                session.add(integration_a)
                await session.flush()
                token_a = OAuthToken(
                    organization_id=org_a_id,
                    integration_id=integration_a.id,
                    encrypted_access_token=encrypt_token("fake-google-access-token"),
                    scopes=["https://www.googleapis.com/auth/calendar.events"],
                )
                session.add(token_a)
                await session.commit()
            print(f"Test orgs/workspaces/projects created. Org A={org_a_id} (calendar connected) Org C={org_c_id} (not connected)")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            headers_c = await create_authenticated_headers(client, org_c_id)

            captured_params = {}

            async def fake_calendar_events(self, url, **kwargs):
                assert "googleapis.com/calendar/v3/calendars/primary/events" in str(url)
                captured_params.update(kwargs.get("params", {}))
                return _fake_response(url, {"items": [
                    {
                        "id": "evt-sync-001",
                        "summary": "Sprint Planning",
                        "start": {"dateTime": "2026-07-20T10:00:00Z"},
                        "end": {"dateTime": "2026-07-20T11:00:00Z"},
                        "attendees": [{"email": "dev1@example.com"}, {"email": "dev2@example.com"}],
                    },
                    {
                        "id": "evt-sync-002",
                        "summary": "Architecture Review",
                        "start": {"dateTime": "2026-07-21T14:00:00Z"},
                        "end": {"dateTime": "2026-07-21T15:00:00Z"},
                        "attendees": [{"email": "dev1@example.com"}],
                    },
                ]})

            # 1. A connected org can sync a date range and gets real events persisted.
            print("\nTest 1: Syncing calendar events for a connected organization...")
            with patch.object(httpx.AsyncClient, "get", new=fake_calendar_events):
                res = await client.post(
                    "/api/v1/integrations/calendar/sync",
                    json={
                        "project_id": str(project_a_id),
                        "start_date": "2026-07-17T00:00:00Z",
                        "end_date": "2026-07-24T00:00:00Z",
                    },
                    headers=headers_a,
                )
            assert res.status_code == 202, f"Expected 202, got {res.status_code}: {res.text}"
            body = res.json()
            assert body["events_synced"] == 2
            assert body["events_found"] == 2
            assert body["status"] == "completed"
            assert "sync_task_id" in body
            assert "timeMin" in captured_params and captured_params["timeMin"] == "2026-07-17T00:00:00+00:00"
            print(f"SUCCESS: Sync completed, events_synced={body['events_synced']}, sync_task_id={body['sync_task_id']}")

            # 2. The synced events must be real, persisted Meeting rows with correctly parsed
            # start/end times and attendee lists.
            print("\nTest 2: Verifying Meeting rows were actually persisted with correct data...")
            async with SessionLocal() as session:
                res_db = await session.execute(select(Meeting).where(Meeting.project_id == project_a_id))
                meetings = {m.external_event_id: m for m in res_db.scalars().all()}
                assert set(meetings.keys()) == {"evt-sync-001", "evt-sync-002"}
                m1 = meetings["evt-sync-001"]
                assert m1.title == "Sprint Planning"
                assert m1.organization_id == org_a_id
                assert m1.start_time == datetime(2026, 7, 20, 10, 0, 0, tzinfo=timezone.utc)
                assert set(m1.attendees) == {"dev1@example.com", "dev2@example.com"}
            print("SUCCESS: Meeting rows correctly persisted with parsed times and attendees.")

            # 3. Re-syncing the same range must update the existing Meeting rows in place,
            # not create duplicates.
            print("\nTest 3: Verifying re-sync updates existing rows instead of duplicating...")
            with patch.object(httpx.AsyncClient, "get", new=fake_calendar_events):
                res = await client.post(
                    "/api/v1/integrations/calendar/sync",
                    json={
                        "project_id": str(project_a_id),
                        "start_date": "2026-07-17T00:00:00Z",
                        "end_date": "2026-07-24T00:00:00Z",
                    },
                    headers=headers_a,
                )
            assert res.status_code == 202
            async with SessionLocal() as session:
                res_db = await session.execute(select(Meeting).where(Meeting.project_id == project_a_id))
                rows = res_db.scalars().all()
                assert len(rows) == 2, f"Expected 2 rows after re-sync (no duplication), found {len(rows)}"
            print("SUCCESS: Re-sync updated existing rows; no duplicates created.")

            # 4. An organization with no active Google Calendar connection must get a clean
            # 400, not a crash.
            print("\nTest 4: Verifying a not-connected organization gets a 400, not a crash...")
            res = await client.post(
                "/api/v1/integrations/calendar/sync",
                json={
                    "project_id": str(project_c_id),
                    "start_date": "2026-07-17T00:00:00Z",
                    "end_date": "2026-07-24T00:00:00Z",
                },
                headers=headers_c,
            )
            assert res.status_code == 400, f"Expected 400 for no calendar connection, got {res.status_code}: {res.text}"
            print("SUCCESS: Not-connected organization correctly rejected with 400.")

            # 5. Cross-tenant: a user from Org B must not be able to sync Org A's project.
            print("\nTest 5: Verifying cross-tenant project access is rejected...")
            res = await client.post(
                "/api/v1/integrations/calendar/sync",
                json={
                    "project_id": str(project_a_id),
                    "start_date": "2026-07-17T00:00:00Z",
                    "end_date": "2026-07-24T00:00:00Z",
                },
                headers=headers_b,
            )
            assert res.status_code == 404, f"Expected 404 for cross-tenant project access, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant calendar sync correctly rejected with 404.")

            # 6. A nonexistent project_id must 404, not 500.
            print("\nTest 6: Verifying a nonexistent project_id returns 404...")
            res = await client.post(
                "/api/v1/integrations/calendar/sync",
                json={
                    "project_id": str(uuid.uuid4()),
                    "start_date": "2026-07-17T00:00:00Z",
                    "end_date": "2026-07-24T00:00:00Z",
                },
                headers=headers_a,
            )
            assert res.status_code == 404, f"Expected 404 for nonexistent project, got {res.status_code}: {res.text}"
            print("SUCCESS: Nonexistent project_id correctly returns 404.")

        finally:
            print("\nCleaning up calendar sync test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id, org_c_id] if o]:
                    for pid in [p for p in [project_a_id, project_c_id] if p]:
                        mt_res = await session.execute(select(Meeting).where(Meeting.project_id == pid))
                        for m in mt_res.scalars().all():
                            await session.delete(m)
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
                    await session.commit()

                    proj_res = await session.execute(select(Project).where(Project.organization_id == oid))
                    for p in proj_res.scalars().all():
                        await session.delete(p)
                    ws_res = await session.execute(select(Workspace).where(Workspace.organization_id == oid))
                    for w in ws_res.scalars().all():
                        await session.delete(w)
                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()

                    org_res = await session.execute(select(Organization).where(Organization.id == oid))
                    db_org = org_res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Google Calendar Sync tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_calendar_sync_flow())
