import asyncio
import uuid
import httpx
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


async def test_calendar_meetings_read_flow():
    print("Initializing Calendar Meetings Read API validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None
    project_empty_id = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Cal Read Org A {suffix}", domain=f"calread-a-{suffix}.com")
                org_b = Organization(name=f"Cal Read Org B {suffix}", domain=f"calread-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Cal Read Workspace A")
                session.add(workspace_a)
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Cal Read Project A")
                project_empty = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Cal Read Project A (no meetings synced)")
                session.add_all([project_a, project_empty])
                await session.flush()
                project_a_id = project_a.id
                project_empty_id = project_empty.id

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
            print(f"Test orgs/workspaces/projects created. Org A={org_a_id} Org B={org_b_id}")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            async def fake_calendar_events(self, url, **kwargs):
                return _fake_response(url, {"items": [
                    {
                        "id": "evt-read-001",
                        "summary": "Sprint Planning",
                        "start": {"dateTime": "2026-07-20T10:00:00Z"},
                        "end": {"dateTime": "2026-07-20T11:00:00Z"},
                        "attendees": [{"email": "dev1@example.com"}, {"email": "dev2@example.com"}],
                    },
                    {
                        "id": "evt-read-002",
                        "summary": "Architecture Review",
                        "start": {"dateTime": "2026-07-21T14:00:00Z"},
                        "end": {"dateTime": "2026-07-21T15:00:00Z"},
                        "attendees": [{"email": "dev1@example.com"}],
                    },
                ]})

            # Seed real Meeting rows via the existing, already-verified sync path.
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
            assert res.status_code == 202, f"Seed sync failed: {res.text}"
            print("Seed sync completed: 2 real Meeting rows persisted for Project A.")

            # 1. The owning organization can list the real, previously-synced meetings, in
            # chronological order, with correctly shaped fields.
            print("\nTest 1: Verifying Org A can list its own project's synced meetings...")
            res = await client.get(
                "/api/v1/integrations/calendar/meetings",
                params={"project_id": str(project_a_id)},
                headers=headers_a,
            )
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            body = res.json()
            assert body["project_id"] == str(project_a_id)
            assert body["total_meetings"] == 2
            titles = [m["title"] for m in body["meetings"]]
            assert titles == ["Sprint Planning", "Architecture Review"], f"Expected chronological order, got {titles}"
            m1 = body["meetings"][0]
            assert m1["external_event_id"] == "evt-read-001"
            assert set(m1["attendees"]) == {"dev1@example.com", "dev2@example.com"}
            assert "start_time" in m1 and "end_time" in m1 and "id" in m1
            print(f"SUCCESS: Org A retrieved {body['total_meetings']} real synced meetings in chronological order.")

            # 2. A project with no synced meetings returns a clean empty list, not an error.
            print("\nTest 2: Verifying a project with no synced meetings returns an empty list...")
            res = await client.get(
                "/api/v1/integrations/calendar/meetings",
                params={"project_id": str(project_empty_id)},
                headers=headers_a,
            )
            assert res.status_code == 200, res.text
            assert res.json()["total_meetings"] == 0
            assert res.json()["meetings"] == []
            print("SUCCESS: Empty meetings list correctly returned for an unsynced project.")

            # 3. THE CRITICAL CHECK: Org B must not be able to read Org A's real meeting data
            # by supplying Org A's project_id.
            print("\nTest 3: Verifying cross-tenant meetings read is rejected...")
            res = await client.get(
                "/api/v1/integrations/calendar/meetings",
                params={"project_id": str(project_a_id)},
                headers=headers_b,
            )
            assert res.status_code == 404, f"Expected 404 for cross-tenant read, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) when attempting to read Org A's meetings.")

            # 4. A nonexistent project_id must 404, not 500.
            print("\nTest 4: Verifying a nonexistent project_id returns 404...")
            res = await client.get(
                "/api/v1/integrations/calendar/meetings",
                params={"project_id": str(uuid.uuid4())},
                headers=headers_a,
            )
            assert res.status_code == 404, f"Expected 404 for nonexistent project, got {res.status_code}: {res.text}"
            print("SUCCESS: Nonexistent project_id correctly returns 404.")

            # 5. Unauthenticated requests must be rejected, unlike the hardcoded GET
            # /google/meetings mock this endpoint is deliberately distinct from.
            print("\nTest 5: Verifying an unauthenticated request is rejected...")
            res = await client.get(
                "/api/v1/integrations/calendar/meetings",
                params={"project_id": str(project_a_id)},
            )
            assert res.status_code in (401, 403), f"Expected 401/403 for unauthenticated request, got {res.status_code}: {res.text}"
            print(f"SUCCESS: Unauthenticated request correctly rejected ({res.status_code}).")

        finally:
            print("\nCleaning up calendar meetings read test database entries...")
            async with SessionLocal() as session:
                for pid in [p for p in [project_a_id, project_empty_id] if p]:
                    mt_res = await session.execute(select(Meeting).where(Meeting.project_id == pid))
                    for m in mt_res.scalars().all():
                        await session.delete(m)
                await session.commit()

                for oid in [o for o in [org_a_id, org_b_id] if o]:
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

    print("\nAll Calendar Meetings Read API tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_calendar_meetings_read_flow())
