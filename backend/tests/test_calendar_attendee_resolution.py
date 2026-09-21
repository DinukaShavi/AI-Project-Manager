import asyncio
import uuid
import httpx
from unittest.mock import patch
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.core.security import encrypt_token, get_password_hash
from app.models.tenant import Organization, Workspace, User, Role
from app.models.project import Project, Meeting
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

GOOGLE_EVENT_ID = "google-created-event-attendee-64"
_real_async_client_post = httpx.AsyncClient.post


def _fake_response(url, json_body, status_code=200):
    return httpx.Response(status_code, request=httpx.Request("POST", str(url)), json=json_body)


async def test_calendar_attendee_resolution_flow():
    print("Initializing Calendar Attendee Resolution (Phase 64) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None
    teammate_id = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Attendee Org A {suffix}", domain=f"attendee-a-{suffix}.com")
                org_b = Organization(name=f"Attendee Org B {suffix}", domain=f"attendee-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Attendee Workspace A")
                session.add(workspace_a)
                await session.flush()
                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Attendee Project A")
                session.add(project_a)
                await session.flush()
                project_a_id = project_a.id

                viewer_role = (await session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()
                teammate = User(
                    organization_id=org_a_id, email=f"teammate-{suffix}@example.com", full_name="Real Teammate",
                    hashed_password=get_password_hash("TestPass123!"),
                )
                teammate.roles.append(viewer_role)
                session.add(teammate)
                await session.flush()
                teammate_id = teammate.id

                integration_a = Integration(organization_id=org_a_id, provider="google_calendar", is_active=True)
                session.add(integration_a)
                await session.flush()
                token_a = OAuthToken(
                    organization_id=org_a_id, integration_id=integration_a.id,
                    encrypted_access_token=encrypt_token("fake-google-access-token"),
                    scopes=["https://www.googleapis.com/auth/calendar.events"],
                )
                session.add(token_a)
                await session.commit()
            print(f"Test orgs/projects created. Org A={org_a_id} (has real teammate {teammate_id}) Org B={org_b_id}")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            # 1. GET /organizations/members/directory is self-service -- a plain (non-admin)
            #    member can see it, unlike GET /organizations/members.
            print("\nTest 1: Verifying the member directory is accessible to a non-admin member...")
            res = await client.get("/api/v1/organizations/members/directory", headers=headers_a)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            body = res.json()
            emails = {m["email"] for m in body["members"]}
            assert f"teammate-{suffix}@example.com" in emails
            assert "roles" not in body["members"][0], "Directory should not expose roles"
            print("SUCCESS: Member directory is self-service and correctly scoped.")

            # 2. Directory is tenant-scoped: Org B never sees Org A's members.
            print("\nTest 2: Verifying the member directory is tenant-scoped...")
            res = await client.get("/api/v1/organizations/members/directory", headers=headers_b)
            assert res.status_code == 200, res.text
            assert f"teammate-{suffix}@example.com" not in {m["email"] for m in res.json()["members"]}
            print("SUCCESS: Org B cannot see Org A's members via the directory.")

            captured_payload = {}

            async def fake_create_event(self, url, **kwargs):
                if "googleapis.com/calendar/v3/calendars/primary/events" not in str(url):
                    return await _real_async_client_post(self, url, **kwargs)
                captured_payload.update(kwargs.get("json", {}))
                return _fake_response(url, {"id": GOOGLE_EVENT_ID, "summary": kwargs["json"]["summary"]}, status_code=200)

            # 3. attendee_user_ids resolves to the real teammate's real email, merged with a
            #    raw attendee_emails entry, deduplicated.
            print("\nTest 3: Verifying attendee_user_ids resolves to a real email and merges with attendee_emails...")
            with patch.object(httpx.AsyncClient, "post", new=fake_create_event):
                res = await client.post(
                    "/api/v1/integrations/calendar/meetings",
                    json={
                        "project_id": str(project_a_id),
                        "title": "Sprint Review",
                        "start_time": "2026-08-20T14:00:00Z",
                        "end_time": "2026-08-20T14:30:00Z",
                        "attendee_user_ids": [str(teammate_id)],
                        "attendee_emails": [f"teammate-{suffix}@example.com", "external-client@example.com"],
                    },
                    headers=headers_a,
                )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            body = res.json()
            assert set(body["attendees"]) == {f"teammate-{suffix}@example.com", "external-client@example.com"}, body["attendees"]
            assert {"email": f"teammate-{suffix}@example.com"} in captured_payload["attendees"]
            assert {"email": "external-client@example.com"} in captured_payload["attendees"]
            print("SUCCESS: Real teammate resolved and deduplicated with the raw email correctly.")

            # 4. An attendee_user_id from a different org -> 404, no event created, no
            #    real Google Calendar API call made.
            print("\nTest 4: Verifying a cross-org attendee_user_id is rejected with 404...")
            async with SessionLocal() as session:
                other_org_user = User(
                    organization_id=org_b_id, email=f"otherorg-{suffix}@example.com", full_name="Other Org User",
                    hashed_password=get_password_hash("TestPass123!"),
                )
                session.add(other_org_user)
                await session.commit()
                other_org_user_id = other_org_user.id

            call_count = {"n": 0}

            async def counting_fake_create_event(self, url, **kwargs):
                if "googleapis.com/calendar/v3/calendars/primary/events" in str(url):
                    call_count["n"] += 1
                return await fake_create_event(self, url, **kwargs)

            with patch.object(httpx.AsyncClient, "post", new=counting_fake_create_event):
                res = await client.post(
                    "/api/v1/integrations/calendar/meetings",
                    json={
                        "project_id": str(project_a_id),
                        "title": "Should not be created",
                        "start_time": "2026-08-21T14:00:00Z",
                        "end_time": "2026-08-21T14:30:00Z",
                        "attendee_user_ids": [str(other_org_user_id)],
                    },
                    headers=headers_a,
                )
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            assert call_count["n"] == 0, "Google Calendar API must not be called when attendee resolution fails"
            print("SUCCESS: Cross-org attendee_user_id correctly rejected with 404, no event created.")

        finally:
            print("\nCleaning up test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    res_db = await session.execute(select(Meeting).where(Meeting.organization_id == oid))
                    for m in res_db.scalars().all():
                        await session.delete(m)
                    res_db = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == oid))
                    for row in res_db.scalars().all():
                        await session.delete(row)
                    await session.flush()
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

    print("\nAll Calendar Attendee Resolution tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_calendar_attendee_resolution_flow())
