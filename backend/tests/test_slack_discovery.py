import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.core.security import encrypt_token
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project, SlackChannelMapping
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from sqlalchemy import select
from tests._auth_helpers import create_authenticated_headers

_real_get = httpx.AsyncClient.get


async def _fake_slack_get(self, url, **kwargs):
    if str(url) == "https://slack.com/api/conversations.list":
        req = httpx.Request("GET", str(url))
        return httpx.Response(200, request=req, json={
            "ok": True,
            "channels": [
                {"id": "C0DISCOVER01", "name": "project-backend", "is_private": False, "num_members": 8, "topic": {"value": "Backend team channel"}},
                {"id": "C0DISCOVER02", "name": "project-frontend", "is_private": True, "num_members": 5, "topic": {"value": ""}},
            ],
        })
    return await _real_get(self, url, **kwargs)


async def test_slack_discovery_flow():
    print("Initializing Slack Channel Discovery validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Slack Discover Org A {suffix}", domain=f"slackdisc-a-{suffix}.com")
                org_b = Organization(name=f"Slack Discover Org B {suffix}", domain=f"slackdisc-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Slack Discover Workspace A")
                session.add(workspace_a)
                await session.flush()
                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Slack Discover Project A")
                session.add(project_a)
                await session.flush()
                project_a_id = project_a.id

                integration_a = Integration(organization_id=org_a_id, provider="slack", is_active=True)
                session.add(integration_a)
                await session.flush()
                token_a = OAuthToken(organization_id=org_a_id, integration_id=integration_a.id, encrypted_access_token=encrypt_token("xoxb-fake-slack-token"))
                session.add(token_a)
                await session.commit()

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            with patch.object(httpx.AsyncClient, "get", new=_fake_slack_get):
                # 1. Discovery returns real channels from the connected token.
                print("\nTest 1: Verifying channel discovery returns real channels...")
                res = await client.get("/api/v1/integrations/slack/discover-channels", headers=headers_a)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
                discovered = res.json()["channels"]
                assert len(discovered) == 2
                assert any(c["slack_channel_id"] == "C0DISCOVER01" and c["name"] == "project-backend" for c in discovered)
                print(f"SUCCESS: Discovered {len(discovered)} real Slack channels.")

            # 2. Discovery without a Slack connection returns a clean 400.
            print("\nTest 2: Verifying discovery fails cleanly for an org with no Slack connection...")
            res = await client.get("/api/v1/integrations/slack/discover-channels", headers=headers_b)
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Not-connected organization correctly rejected with 400.")

            # 3. Map a discovered channel, then read it back via the real mapped-channels list.
            print("\nTest 3: Mapping a discovered channel, then reading it back...")
            res = await client.post(
                "/api/v1/integrations/slack/mappings",
                json={"project_id": str(project_a_id), "slack_channel_id": "C0DISCOVER01"},
                headers=headers_a,
            )
            assert res.status_code == 200, res.text

            res = await client.get(f"/api/v1/integrations/slack/mapped-channels?project_id={project_a_id}", headers=headers_a)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            mapped = res.json()["channels"]
            assert len(mapped) == 1
            assert mapped[0]["slack_channel_id"] == "C0DISCOVER01"
            print("SUCCESS: Mapped channel correctly appears in the real mapped-channels list.")

            # 4. Cross-tenant: Org B cannot read Org A's mapped channels.
            print("\nTest 4: Verifying cross-tenant isolation on mapped-channels...")
            res = await client.get(f"/api/v1/integrations/slack/mapped-channels?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant mapped-channels access correctly rejected (404).")

            # 5. A nonexistent project_id returns 404, not a crash.
            print("\nTest 5: Verifying a nonexistent project_id returns 404...")
            res = await client.get(f"/api/v1/integrations/slack/mapped-channels?project_id={uuid.uuid4()}", headers=headers_a)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Nonexistent project_id correctly returns 404.")

        finally:
            print("\nCleaning up Slack discovery test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    if project_a_id:
                        map_res = await session.execute(select(SlackChannelMapping).where(SlackChannelMapping.project_id == project_a_id))
                        for m in map_res.scalars().all():
                            await session.delete(m)
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

    print("\nAll Slack Channel Discovery tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_slack_discovery_flow())
