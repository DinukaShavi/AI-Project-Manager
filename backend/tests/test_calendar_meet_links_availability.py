import asyncio
import uuid
import httpx
from datetime import datetime, timedelta, timezone
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

GOOGLE_EVENT_ID = "google-created-event-meet65"
MEET_URL = "https://meet.google.com/xyz-abcd-efg"
_real_async_client_post = httpx.AsyncClient.post


def _fake_response(url, json_body, status_code=200):
    return httpx.Response(status_code, request=httpx.Request("POST", str(url)), json=json_body)


async def test_calendar_meet_links_availability_flow():
    print("Initializing Real Meet Links & Team Availability (Phase 65) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Meet Avail Org A {suffix}", domain=f"meetavail-a-{suffix}.com")
                org_b = Organization(name=f"Meet Avail Org B {suffix}", domain=f"meetavail-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Meet Avail Workspace A")
                session.add(workspace_a)
                await session.flush()
                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Meet Avail Project A")
                session.add(project_a)
                await session.flush()
                project_a_id = project_a.id

                viewer_role = (await session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()
                busy_member = User(
                    organization_id=org_a_id, email=f"busy-{suffix}@example.com", full_name="Busy Member",
                    hashed_password=get_password_hash("TestPass123!"),
                )
                free_member = User(
                    organization_id=org_a_id, email=f"free-{suffix}@example.com", full_name="Free Member",
                    hashed_password=get_password_hash("TestPass123!"),
                )
                busy_member.roles.append(viewer_role)
                free_member.roles.append(viewer_role)
                session.add_all([busy_member, free_member])
                await session.flush()

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
            print(f"Test orgs/projects created. Org A={org_a_id} (2 real members) Org B={org_b_id} (not connected)")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            captured_payload = {}

            async def fake_create_event(self, url, **kwargs):
                if "googleapis.com/calendar/v3/calendars/primary/events" not in str(url):
                    return await _real_async_client_post(self, url, **kwargs)
                captured_payload.update(kwargs.get("json", {}))
                assert kwargs.get("params", {}).get("conferenceDataVersion") == 1
                return _fake_response(url, {
                    "id": GOOGLE_EVENT_ID,
                    "summary": kwargs["json"]["summary"],
                    "conferenceData": {"entryPoints": [{"entryPointType": "video", "uri": MEET_URL}]},
                }, status_code=200)

            # 1. A newly created event requests a real Meet link, and it's stored + returned.
            print("\nTest 1: Verifying event creation requests and stores a real Meet link...")
            with patch.object(httpx.AsyncClient, "post", new=fake_create_event):
                res = await client.post(
                    "/api/v1/integrations/calendar/meetings",
                    json={
                        "project_id": str(project_a_id),
                        "title": "Sprint Review",
                        "start_time": "2026-08-20T14:00:00Z",
                        "end_time": "2026-08-20T14:30:00Z",
                    },
                    headers=headers_a,
                )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            assert res.json()["meet_link"] == MEET_URL
            print("SUCCESS: Real Meet link requested at creation time and returned.")

            # 2. GET /calendar/meetings surfaces the stored meet_link.
            print("\nTest 2: Verifying GET /calendar/meetings surfaces the real meet_link...")
            res = await client.get(f"/api/v1/integrations/calendar/meetings?project_id={project_a_id}", headers=headers_a)
            assert res.status_code == 200, res.text
            assert res.json()["meetings"][0]["meet_link"] == MEET_URL
            print("SUCCESS: Real meet_link correctly surfaced via the listing endpoint.")

            # 3. Old mock routes are gone.
            print("\nTest 3: Verifying the old mock routes no longer exist...")
            res = await client.get("/api/v1/integrations/google/meetings")
            assert res.status_code == 404, f"Expected 404, got {res.status_code}"
            res = await client.get("/api/v1/integrations/google/availability")
            assert res.status_code == 404, f"Expected 404, got {res.status_code}"
            print("SUCCESS: Old mock routes correctly removed (404).")

            # 4. Real team availability: a member with a busy interval overlapping a candidate
            #    slot is excluded from it; a member with no conflict is included.
            print("\nTest 4: Verifying real team availability correctly reflects real busy intervals...")
            start_date = "2026-08-24T00:00:00Z"
            end_date = "2026-08-25T00:00:00Z"

            async def fake_freebusy(self, url, **kwargs):
                if "googleapis.com/calendar/v3/freeBusy" not in str(url):
                    return await _real_async_client_post(self, url, **kwargs)
                return _fake_response(url, {
                    "calendars": {
                        f"busy-{suffix}@example.com": {"busy": [{"start": "2026-08-24T10:00:00Z", "end": "2026-08-24T11:00:00Z"}]},
                        f"free-{suffix}@example.com": {"busy": []},
                    }
                })

            with patch.object(httpx.AsyncClient, "post", new=fake_freebusy):
                res = await client.get(
                    "/api/v1/integrations/calendar/availability",
                    params={"start_date": start_date, "end_date": end_date},
                    headers=headers_a,
                )
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            slots = res.json()["available_slots"]
            slot_10am = next((s for s in slots if s["date"] == "2026-08-24" and s["slot"].startswith("10:00")), None)
            assert slot_10am is not None, f"Expected a 10:00 slot in {slots}"
            assert "Busy Member" not in slot_10am["participants_available"]
            assert "Free Member" in slot_10am["participants_available"]
            print("SUCCESS: Real availability correctly excludes the busy member and includes the free member.")

            # 5. Calendar not connected -> 400.
            print("\nTest 5: Verifying a not-connected organization gets a 400 on availability...")
            res = await client.get(
                "/api/v1/integrations/calendar/availability",
                params={"start_date": start_date, "end_date": end_date},
                headers=headers_b,
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Not-connected organization correctly rejected with 400.")

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

    print("\nAll Real Meet Links & Team Availability tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_calendar_meet_links_availability_flow())
