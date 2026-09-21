import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.core.security import encrypt_token, get_password_hash
from app.models.tenant import Organization, Workspace, User, Role
from app.models.project import Project, Meeting
from app.models.integration import Integration, OAuthToken
from app.models.context import ContextChunk, ContextEmbedding
from app.models.graph import KnowledgeGraphEdge, ContextSnapshot
from app.services.context_ingestion import derive_source_id
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

_real_get = httpx.AsyncClient.get
_real_post = httpx.AsyncClient.post
SYNCED_EVENT_ID = "google-synced-event-ctx73"
CREATED_EVENT_ID = "google-created-event-ctx73"


async def _get_chunks(session, organization_id, source_type, external_id):
    source_id = derive_source_id("calendar", external_id)
    res = await session.execute(
        select(ContextChunk).where(
            ContextChunk.organization_id == organization_id,
            ContextChunk.source_type == source_type,
            ContextChunk.source_id == source_id,
        )
    )
    return list(res.scalars().all())


async def test_calendar_context_ingestion_flow():
    print("Initializing Calendar Context Ingestion (Phase 73) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_c_id = None
    project_a_id = None
    created_chunk_ids = []
    alice_email = f"alice-{suffix}@example.com"
    bob_email = f"bob-{suffix}@example.com"

    async def fake_list_events(self, url, **kwargs):
        if "googleapis.com/calendar/v3/calendars/primary/events" not in str(url):
            return await _real_get(self, url, **kwargs)
        req = httpx.Request("GET", str(url))
        return httpx.Response(200, request=req, json={"items": [
            {
                "id": SYNCED_EVENT_ID,
                "summary": f"Sprint Review {suffix}",
                "description": "Discuss real ingestion pipeline coverage.",
                "start": {"dateTime": "2026-08-24T14:00:00Z"},
                "end": {"dateTime": "2026-08-24T14:30:00Z"},
                "attendees": [{"email": alice_email}, {"email": bob_email}],
                "htmlLink": f"https://calendar.google.com/event?eid={SYNCED_EVENT_ID}",
            },
        ]})

    async def fake_create_event(self, url, **kwargs):
        if "googleapis.com/calendar/v3/calendars/primary/events" not in str(url):
            return await _real_post(self, url, **kwargs)
        req = httpx.Request("POST", str(url))
        return httpx.Response(200, request=req, json={
            "id": CREATED_EVENT_ID,
            "summary": kwargs["json"]["summary"],
            "htmlLink": f"https://calendar.google.com/event?eid={CREATED_EVENT_ID}",
        })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Cal Ctx Org A {suffix}", domain=f"calctx-a-{suffix}.com")
                session.add(org_a)
                await session.flush()
                org_a_id = org_a.id

                workspace_a = Workspace(organization_id=org_a_id, name="Cal Ctx Workspace A")
                session.add(workspace_a)
                await session.flush()
                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Cal Ctx Project A")
                session.add(project_a)
                await session.flush()
                project_a_id = project_a.id

                integration_a = Integration(organization_id=org_a_id, provider="google_calendar", is_active=True)
                session.add(integration_a)
                await session.flush()
                token_a = OAuthToken(
                    organization_id=org_a_id, integration_id=integration_a.id,
                    encrypted_access_token=encrypt_token("fake-google-access-token"),
                    scopes=["https://www.googleapis.com/auth/calendar.events"],
                )
                session.add(token_a)

                # Org C: unrelated organization with a real User whose email happens to match
                # the second attendee's email -- proves the resolution lookup is org-scoped,
                # not a global email match across tenants.
                org_c = Organization(name=f"Cal Ctx Org C {suffix}", domain=f"calctx-c-{suffix}.com")
                session.add(org_c)
                await session.flush()
                org_c_id = org_c.id
                viewer_role = (await session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()
                bob_in_org_c = User(
                    organization_id=org_c_id, email=bob_email, full_name="Bob (Org C)",
                    hashed_password=get_password_hash("TestPass123!"),
                )
                bob_in_org_c.roles.append(viewer_role)
                session.add(bob_in_org_c)
                await session.commit()
            print(f"Test org/project created. Org A={org_a_id} Project={project_a_id} Org C={org_c_id} (unrelated, has a User with bob's email)")

            # Org A's authenticated user's email is deliberately alice's real attendee email,
            # so alice's ATTENDS edge should resolve to a real internal User; bob only exists
            # as a User in the unrelated Org C, so his edge must stay a raw-email URN.
            headers_a = await create_authenticated_headers(client, org_a_id, email=alice_email)

            # 1. A real synced meeting is fed into the real centralized context pipeline:
            #    indexed as a ContextChunk, a real ATTENDS graph edge per attendee, and a
            #    stale ContextSnapshot regenerated -- same pipeline GitHub/Jira/Slack already
            #    proved (Phase 58/59/68), now for Calendar.
            print("\nTest 1: Verifying a real synced meeting is indexed into the context pipeline...")
            with patch.object(httpx.AsyncClient, "get", new=fake_list_events):
                res = await client.post(
                    "/api/v1/integrations/calendar/sync",
                    json={
                        "project_id": str(project_a_id),
                        "start_date": "2026-08-24T00:00:00Z",
                        "end_date": "2026-08-25T00:00:00Z",
                    },
                    headers=headers_a,
                )
            assert res.status_code == 202, f"Expected 202, got {res.status_code}: {res.text}"

            async with SessionLocal() as session:
                chunks = await _get_chunks(session, org_a_id, "calendar_meeting", SYNCED_EVENT_ID)
                assert len(chunks) > 0, "Expected the synced meeting to be indexed as a real ContextChunk"
                assert f"Sprint Review {suffix}" in chunks[0].content
                assert "Discuss real ingestion pipeline coverage." in chunks[0].content
                assert chunks[0].project_id == project_a_id
                created_chunk_ids.extend(c.id for c in chunks)
            print("SUCCESS: Real synced meeting indexed with correct content and project_id.")

            print("\nTest 2: Verifying ATTENDS edges resolve a real matched attendee to a real User, and leave an unmatched/cross-tenant attendee as a raw-email URN (Phase 74)...")
            async with SessionLocal() as session:
                res = await session.execute(
                    select(KnowledgeGraphEdge).where(
                        KnowledgeGraphEdge.project_id == project_a_id,
                        KnowledgeGraphEdge.relation_type == "ATTENDS",
                    )
                )
                edges = list(res.scalars().all())
                targets = {e.target_urn for e in edges}

                alice_res = await session.execute(select(User).where(User.email == alice_email))
                alice_user = alice_res.scalar_one()
                assert f"urn:user:id:{alice_user.id}" in targets, "Alice (a real User in this org) should resolve to a real internal User URN"
                assert f"urn:user:email:{alice_email}" not in targets, "Alice should not also appear as an unresolved raw-email URN"

                assert f"urn:user:email:{bob_email}" in targets, "Bob (a User only in an unrelated org) must stay a raw-email URN -- resolution is org-scoped"
            print("SUCCESS: ATTENDS edges correctly resolved the real matched attendee and left the cross-tenant/unmatched attendee as a raw-email URN.")

            print("\nTest 3: Verifying the project's ContextSnapshot was regenerated...")
            async with SessionLocal() as session:
                res = await session.execute(
                    select(ContextSnapshot).where(ContextSnapshot.project_id == project_a_id)
                )
                snapshot = res.scalars().first()
                assert snapshot is not None, "Expected a real ContextSnapshot to have been generated"
            print("SUCCESS: Real ContextSnapshot generated from real calendar activity.")

            # 4. A real created meeting (the write path) is also fed into the pipeline.
            print("\nTest 4: Verifying a real created meeting is also indexed into the context pipeline...")
            with patch.object(httpx.AsyncClient, "post", new=fake_create_event):
                res = await client.post(
                    "/api/v1/integrations/calendar/meetings",
                    json={
                        "project_id": str(project_a_id),
                        "title": "Architecture Sync",
                        "start_time": "2026-08-26T10:00:00Z",
                        "end_time": "2026-08-26T10:30:00Z",
                        "description": "Real create-path ingestion coverage.",
                    },
                    headers=headers_a,
                )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"

            async with SessionLocal() as session:
                chunks = await _get_chunks(session, org_a_id, "calendar_meeting", CREATED_EVENT_ID)
                assert len(chunks) > 0, "Expected the created meeting to be indexed as a real ContextChunk"
                assert "Architecture Sync" in chunks[0].content
                assert chunks[0].project_id == project_a_id
                created_chunk_ids.extend(c.id for c in chunks)
            print("SUCCESS: Real created meeting indexed with correct content and project_id.")

        finally:
            print("\nCleaning up test database entries...")
            async with SessionLocal() as session:
                for cid in created_chunk_ids:
                    res = await session.execute(select(ContextEmbedding).where(ContextEmbedding.chunk_id == cid))
                    for emb in res.scalars().all():
                        await session.delete(emb)
                    res = await session.execute(select(ContextChunk).where(ContextChunk.id == cid))
                    chk = res.scalar_one_or_none()
                    if chk:
                        await session.delete(chk)
                await session.flush()
                if project_a_id:
                    for model in (KnowledgeGraphEdge, ContextSnapshot, Meeting):
                        res = await session.execute(select(model).where(model.project_id == project_a_id))
                        for row in res.scalars().all():
                            await session.delete(row)
                    await session.flush()
                if org_a_id:
                    res = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == org_a_id))
                    for row in res.scalars().all():
                        await session.delete(row)
                    res = await session.execute(select(Integration).where(Integration.organization_id == org_a_id))
                    for i in res.scalars().all():
                        await session.delete(i)
                    await session.flush()
                    if project_a_id:
                        res = await session.execute(select(Project).where(Project.id == project_a_id))
                        p = res.scalar_one_or_none()
                        if p:
                            await session.delete(p)
                    res = await session.execute(select(Workspace).where(Workspace.organization_id == org_a_id))
                    for w in res.scalars().all():
                        await session.delete(w)
                    res = await session.execute(select(User).where(User.organization_id == org_a_id))
                    for u in res.scalars().all():
                        await session.delete(u)
                    await session.flush()
                    org_row = await session.get(Organization, org_a_id)
                    if org_row:
                        await session.delete(org_row)
                if org_c_id:
                    res = await session.execute(select(User).where(User.organization_id == org_c_id))
                    for u in res.scalars().all():
                        await session.delete(u)
                    await session.flush()
                    org_c_row = await session.get(Organization, org_c_id)
                    if org_c_row:
                        await session.delete(org_c_row)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Calendar Context Ingestion tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_calendar_context_ingestion_flow())
