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
from app.models.audit import AuditLog
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

GOOGLE_EVENT_ID = "google-created-event-abc123"
_real_async_client_post = httpx.AsyncClient.post


def _fake_response(url, json_body, status_code=200):
    return httpx.Response(status_code, request=httpx.Request("POST", str(url)), json=json_body)


async def test_calendar_event_creation_flow():
    print("Initializing Google Calendar Event Creation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_c_id = None
    project_a_id = None
    project_c_id = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Cal Create Org A {suffix}", domain=f"calcreate-a-{suffix}.com")
                org_c = Organization(name=f"Cal Create Org C {suffix}", domain=f"calcreate-c-{suffix}.com")
                session.add_all([org_a, org_c])
                await session.flush()
                org_a_id, org_c_id = org_a.id, org_c.id

                workspace_a = Workspace(organization_id=org_a_id, name="Cal Create Workspace A")
                workspace_c = Workspace(organization_id=org_c_id, name="Cal Create Workspace C")
                session.add_all([workspace_a, workspace_c])
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Cal Create Project A")
                project_c = Project(organization_id=org_c_id, workspace_id=workspace_c.id, name="Cal Create Project C (no calendar connected)")
                session.add_all([project_a, project_c])
                await session.flush()
                project_a_id = project_a.id
                project_c_id = project_c.id

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

            captured_payload = {}

            async def fake_create_event(self, url, **kwargs):
                if "googleapis.com/calendar/v3/calendars/primary/events" not in str(url):
                    return await _real_async_client_post(self, url, **kwargs)
                captured_payload.update(kwargs.get("json", {}))
                return _fake_response(url, {
                    "id": GOOGLE_EVENT_ID,
                    "summary": kwargs["json"]["summary"],
                    "htmlLink": f"https://calendar.google.com/event?eid={GOOGLE_EVENT_ID}",
                }, status_code=200)

            start_time = "2026-08-20T14:00:00Z"
            end_time = "2026-08-20T14:30:00Z"

            # 1. A connected org can create a real event; a real Meeting row is persisted.
            print("\nTest 1: Creating a real Google Calendar event for a connected organization...")
            with patch.object(httpx.AsyncClient, "post", new=fake_create_event):
                res = await client.post(
                    "/api/v1/integrations/calendar/meetings",
                    json={
                        "project_id": str(project_a_id),
                        "title": "Sprint Blocker Review",
                        "start_time": start_time,
                        "end_time": end_time,
                        "attendee_emails": ["dev1@example.com", "dev2@example.com"],
                        "description": "Discuss blockers surfaced by the AI recommendation engine.",
                    },
                    headers=headers_a,
                )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            body = res.json()
            assert body["external_event_id"] == GOOGLE_EVENT_ID
            assert body["title"] == "Sprint Blocker Review"
            assert set(body["attendees"]) == {"dev1@example.com", "dev2@example.com"}
            meeting_id = body["id"]
            print(f"SUCCESS: Real event created, external_event_id={GOOGLE_EVENT_ID}.")

            # 2. Google's API was actually called with the correct real payload.
            print("\nTest 2: Verifying the real Google Calendar API payload construction...")
            assert captured_payload["summary"] == "Sprint Blocker Review"
            # Pydantic normalizes the "Z" suffix to "+00:00" on parse; compare as datetimes,
            # not raw strings.
            assert datetime.fromisoformat(captured_payload["start"]["dateTime"]) == datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            assert {"email": "dev1@example.com"} in captured_payload["attendees"]
            print("SUCCESS: Real request payload correctly constructed.")

            # 3. The created meeting is immediately readable via GET /calendar/meetings.
            print("\nTest 3: Verifying the created meeting appears immediately in GET /calendar/meetings...")
            res = await client.get(
                "/api/v1/integrations/calendar/meetings",
                params={"project_id": str(project_a_id)},
                headers=headers_a,
            )
            assert res.status_code == 200
            assert any(m["id"] == meeting_id for m in res.json()["meetings"])
            print("SUCCESS: Created meeting immediately visible via the read endpoint.")

            async with SessionLocal() as session:
                meeting_row = await session.get(Meeting, uuid.UUID(meeting_id))
                assert meeting_row is not None
                assert meeting_row.organization_id == org_a_id
                assert meeting_row.project_id == project_a_id
                assert meeting_row.external_event_id == GOOGLE_EVENT_ID

            # 4. An organization with no active Google Calendar connection gets a clean 400.
            print("\nTest 4: Verifying a not-connected organization gets a 400, not a crash...")
            res = await client.post(
                "/api/v1/integrations/calendar/meetings",
                json={"project_id": str(project_c_id), "title": "Should Fail", "start_time": start_time, "end_time": end_time},
                headers=await create_authenticated_headers(client, org_c_id),
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Not-connected organization correctly rejected with 400.")

            # 5. THE CRITICAL CHECK: Org A must not be able to create a calendar event
            # attached to Org C's real project, even though Org A has its own valid Calendar
            # connection -- that connection must never be usable against another org's project.
            print("\nTest 5: Verifying Org A cannot create an event on Org C's real project...")
            with patch.object(httpx.AsyncClient, "post", new=fake_create_event):
                res = await client.post(
                    "/api/v1/integrations/calendar/meetings",
                    json={"project_id": str(project_c_id), "title": "Cross-Tenant Attempt", "start_time": start_time, "end_time": end_time},
                    headers=headers_a,
                )
            assert res.status_code == 404, f"Expected 404 for cross-tenant project, got {res.status_code}: {res.text}"
            async with SessionLocal() as session:
                leaked = await session.execute(select(Meeting).where(Meeting.project_id == project_c_id))
                assert leaked.scalars().first() is None, "Org A's rejected attempt must not have created a Meeting on Org C's project"
            print("SUCCESS: Cross-tenant event creation correctly rejected (404); no Meeting row created.")

            # 6. A nonexistent project_id returns 404, not a crash.
            print("\nTest 6: Verifying a nonexistent project_id returns 404...")
            res = await client.post(
                "/api/v1/integrations/calendar/meetings",
                json={"project_id": str(uuid.uuid4()), "title": "Ghost Project Meeting", "start_time": start_time, "end_time": end_time},
                headers=headers_a,
            )
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Nonexistent project_id correctly returns 404.")

            # 7. Audit log records the action with no credential material.
            print("\nTest 7: Verifying the audit log entry is safe and complete...")
            async with SessionLocal() as session:
                audit_res = await session.execute(
                    select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "calendar:event_create")
                )
                rows = audit_res.scalars().all()
                assert len(rows) == 1
                assert rows[0].details["title"] == "Sprint Blocker Review"
                assert "fake-google-access-token" not in str(rows[0].details)
            print("SUCCESS: Audit entry present and free of credential material.")

        finally:
            print("\nCleaning up calendar event creation test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_c_id] if o]:
                    for pid in [p for p in [project_a_id, project_c_id] if p]:
                        mt_res = await session.execute(select(Meeting).where(Meeting.project_id == pid))
                        for m in mt_res.scalars().all():
                            await session.delete(m)
                    await session.commit()

                    audit_res = await session.execute(select(AuditLog).where(AuditLog.organization_id == oid))
                    for a in audit_res.scalars().all():
                        await session.delete(a)
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
                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()

                    org_row = await session.get(Organization, oid)
                    if org_row:
                        await session.delete(org_row)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Google Calendar Event Creation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_calendar_event_creation_flow())
