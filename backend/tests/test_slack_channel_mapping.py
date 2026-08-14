import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project, SlackChannelMapping
from app.models.event import Event
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_slack_channel_mapping_flow():
    print("Initializing Slack Channel Mapping validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None
    project_a2_id = None
    channel_id = f"C{uuid.uuid4().hex[:9].upper()}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Slack Map Org A {suffix}", domain=f"slackmap-a-{suffix}.com")
                org_b = Organization(name=f"Slack Map Org B {suffix}", domain=f"slackmap-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Slack Map Workspace A")
                session.add(workspace_a)
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Slack Map Project A")
                project_a2 = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Slack Map Project A2")
                session.add_all([project_a, project_a2])
                await session.commit()
                project_a_id = project_a.id
                project_a2_id = project_a2.id
            print(f"Test orgs/workspace/projects created. Org A={org_a_id} Org B={org_b_id} Project A={project_a_id} Project A2={project_a2_id}")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            # 1. Mapping a channel to an owned project succeeds (200) and returns the
            # documented status confirmation payload (api_contract.md section 6.A).
            print("\nTest 1: Mapping a Slack channel to an owned project...")
            res = await client.post(
                "/api/v1/integrations/slack/mappings",
                json={"project_id": str(project_a_id), "slack_channel_id": channel_id},
                headers=headers_a,
            )
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            body = res.json()
            assert body["project_id"] == str(project_a_id)
            assert body["slack_channel_id"] == channel_id
            assert body["status"] == "mapped"
            mapping_id = body["id"]
            print(f"SUCCESS: Channel mapped, id={mapping_id}")

            # 2. The mapping must be a real, persisted row.
            print("\nTest 2: Verifying the mapping row was actually persisted...")
            async with SessionLocal() as session:
                res_db = await session.execute(select(SlackChannelMapping).where(SlackChannelMapping.id == uuid.UUID(mapping_id)))
                mapping = res_db.scalar_one_or_none()
                assert mapping is not None
                assert mapping.organization_id == org_a_id
                assert mapping.project_id == project_a_id
            print("SUCCESS: Mapping row persisted with correct tenant scoping.")

            # 3. Re-mapping the same channel to a DIFFERENT project in the SAME org updates
            # in place, it doesn't create a duplicate mapping.
            print("\nTest 3: Verifying re-mapping the same channel updates in place...")
            res = await client.post(
                "/api/v1/integrations/slack/mappings",
                json={"project_id": str(project_a2_id), "slack_channel_id": channel_id},
                headers=headers_a,
            )
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            assert res.json()["id"] == mapping_id
            assert res.json()["project_id"] == str(project_a2_id)
            async with SessionLocal() as session:
                res_db = await session.execute(select(SlackChannelMapping).where(SlackChannelMapping.slack_channel_id == channel_id))
                rows = res_db.scalars().all()
                assert len(rows) == 1, f"Expected exactly 1 row after re-map, found {len(rows)}"
                assert rows[0].project_id == project_a2_id
            print("SUCCESS: Re-mapping updated the existing row in place; no duplicates.")

            # 4. A DIFFERENT organization must not be able to claim a channel already mapped
            # to another org's project (cross-tenant conflict).
            print("\nTest 4: Verifying cross-tenant channel claim is rejected...")
            async with SessionLocal() as session:
                workspace_b = Workspace(organization_id=org_b_id, name="Slack Map Workspace B")
                session.add(workspace_b)
                await session.flush()
                project_b = Project(organization_id=org_b_id, workspace_id=workspace_b.id, name="Slack Map Project B")
                session.add(project_b)
                await session.commit()
                project_b_id = project_b.id

            res = await client.post(
                "/api/v1/integrations/slack/mappings",
                json={"project_id": str(project_b_id), "slack_channel_id": channel_id},
                headers=headers_b,
            )
            assert res.status_code == 409, f"Expected 409 for cross-tenant channel claim, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant channel claim correctly rejected with 409.")

            # 5. Mapping to a nonexistent project must 404.
            print("\nTest 5: Verifying a nonexistent project_id returns 404...")
            res = await client.post(
                "/api/v1/integrations/slack/mappings",
                json={"project_id": str(uuid.uuid4()), "slack_channel_id": f"C{uuid.uuid4().hex[:9].upper()}"},
                headers=headers_a,
            )
            assert res.status_code == 404, f"Expected 404 for nonexistent project, got {res.status_code}: {res.text}"
            print("SUCCESS: Nonexistent project_id correctly returns 404.")

            # 6. An incoming Slack webhook message on the mapped channel, with no explicit
            # project_id, must auto-route to the mapped project (project_a2, per Test 3).
            print("\nTest 6: Verifying webhook messages on a mapped channel auto-route to the correct project...")
            res = await client.post(
                f"/api/v1/integrations/slack/webhook?organization_id={org_a_id}",
                json={
                    "type": "event_callback",
                    "event": {"type": "message", "channel": channel_id, "user": "U0112233", "text": "Deploying now"},
                },
            )
            assert res.status_code == 200, f"Expected 200 (slack/webhook has no explicit status_code, unlike the other provider webhooks), got {res.status_code}: {res.text}"
            event_id = res.json()["event_id"]
            async with SessionLocal() as session:
                res_db = await session.execute(select(Event).where(Event.id == uuid.UUID(event_id)))
                db_event = res_db.scalar_one()
                assert db_event.project_id == project_a2_id, f"Expected auto-routed project_id={project_a2_id}, got {db_event.project_id}"
            print("SUCCESS: Webhook message auto-routed to the mapped project via channel lookup.")

        finally:
            print("\nCleaning up Slack channel mapping test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    ev_res = await session.execute(select(Event).where(Event.organization_id == oid))
                    for ev in ev_res.scalars().all():
                        await session.delete(ev)
                    map_res = await session.execute(select(SlackChannelMapping).where(SlackChannelMapping.organization_id == oid))
                    for m in map_res.scalars().all():
                        await session.delete(m)
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

    print("\nAll Slack Channel Mapping tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_slack_channel_mapping_flow())
