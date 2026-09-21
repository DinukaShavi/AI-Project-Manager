import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

import app.db.base  # Register models
from app.main import app
from app.core.security import encrypt_token
from app.models.tenant import Organization, Workspace
from app.models.project import Project, SlackChannelMapping
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

_real_get = httpx.AsyncClient.get
CHANNEL_ID = "C0SLACK63"


async def _fake_slack_get(self, url, **kwargs):
    url_s = str(url)
    if url_s == "https://slack.com/api/users.list":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"ok": True, "members": [
            {"id": "U100", "name": "alice", "is_admin": True, "is_bot": False, "deleted": False, "profile": {"real_name": "Alice Smith", "status_text": "Building"}},
            {"id": "U200", "name": "deleted-user", "deleted": True, "profile": {}},
        ]})
    if url_s == "https://slack.com/api/conversations.history":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"ok": True, "messages": [
            {"ts": "1721890000.000100", "user": "U100", "text": "Deploying now"},
        ]})
    return await _real_get(self, url, **kwargs)


async def test_slack_real_users_messages_flow():
    print("Initializing Real Slack Users & Messages (Phase 63) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    org_c_id = None
    project_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Slack Dash Org A {suffix}", domain=f"slackdash-a-{suffix}.com")
                org_b = Organization(name=f"Slack Dash Org B {suffix}", domain=f"slackdash-b-{suffix}.com")
                org_c = Organization(name=f"Slack Dash Org C {suffix}", domain=f"slackdash-c-{suffix}.com")
                session.add_all([org_a, org_b, org_c])
                await session.flush()
                org_a_id, org_b_id, org_c_id = org_a.id, org_b.id, org_c.id

                workspace_a = Workspace(organization_id=org_a_id, name="Slack Dash Workspace A")
                session.add(workspace_a)
                await session.flush()
                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Slack Dash Project A")
                session.add(project_a)
                await session.flush()
                project_a_id = project_a.id

                mapping = SlackChannelMapping(organization_id=org_a_id, project_id=project_a_id, slack_channel_id=CHANNEL_ID)
                session.add(mapping)

                integration_a = Integration(organization_id=org_a_id, provider="slack", is_active=True)
                integration_b = Integration(organization_id=org_b_id, provider="slack", is_active=True)
                session.add_all([integration_a, integration_b])
                await session.flush()
                token_a = OAuthToken(organization_id=org_a_id, integration_id=integration_a.id, encrypted_access_token=encrypt_token("fake-slack-bot-token"), scopes=["users:read", "channels:history"])
                token_b = OAuthToken(organization_id=org_b_id, integration_id=integration_b.id, encrypted_access_token=encrypt_token("fake-slack-bot-token-b"), scopes=["users:read", "channels:history"])
                session.add_all([token_a, token_b])
                await session.commit()
            print(f"Test orgs/projects created. Org A={org_a_id} (Slack connected, channel {CHANNEL_ID} mapped) Org B={org_b_id} (Slack connected, no mapping)")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            headers_c = await create_authenticated_headers(client, org_c_id)

            with patch.object(httpx.AsyncClient, "get", new=_fake_slack_get):
                # 1. Real users, deleted users excluded.
                print("\nTest 1: Verifying real Slack user data is returned, deleted users excluded...")
                res = await client.get("/api/v1/integrations/slack/users", headers=headers_a)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
                body = res.json()
                assert body["total_users"] == 1
                assert body["users"][0]["real_name"] == "Alice Smith"
                assert body["users"][0]["role"] == "Admin"
                print("SUCCESS: Real Slack user data correctly returned, deleted user excluded.")

                # 2. Real messages for a mapped channel, with real display-name resolution.
                print("\nTest 2: Verifying real Slack message data is returned with resolved author name...")
                res = await client.get(f"/api/v1/integrations/slack/messages?channel_id={CHANNEL_ID}", headers=headers_a)
                assert res.status_code == 200, res.text
                body = res.json()
                assert body["total_messages"] == 1
                assert body["messages"][0]["text"] == "Deploying now"
                assert body["messages"][0]["user_name"] == "Alice Smith"
                assert body["messages"][0]["timestamp"] == "2024-07-25T06:46:40.000100+00:00"
                print("SUCCESS: Real Slack message data correctly returned with resolved author name.")

                # 3. A channel not mapped to this org -> 404.
                print("\nTest 3: Verifying an unmapped channel_id returns 404...")
                res = await client.get("/api/v1/integrations/slack/messages?channel_id=C0NOTMAPPED", headers=headers_a)
                assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
                print("SUCCESS: Unmapped channel_id correctly returns 404.")

            # 4. Slack not connected for the org -> 400.
            print("\nTest 4: Verifying a not-connected organization gets a 400...")
            res = await client.get("/api/v1/integrations/slack/users", headers=headers_c)
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Not-connected organization correctly rejected with 400.")

            # 5. Cross-tenant isolation: Org B (Slack connected, but no mapping of its own)
            # cannot read Org A's mapped-channel messages.
            print("\nTest 5: Verifying cross-tenant isolation on messages...")
            res = await client.get(f"/api/v1/integrations/slack/messages?channel_id={CHANNEL_ID}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant access correctly rejected (404).")

        finally:
            print("\nCleaning up test database entries...")
            async with SessionLocal() as session:
                from app.models.tenant import User
                from sqlalchemy import select
                for oid in [o for o in [org_a_id, org_b_id, org_c_id] if o]:
                    res_db = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == oid))
                    for row in res_db.scalars().all():
                        await session.delete(row)
                    await session.flush()
                    int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                    for i in int_res.scalars().all():
                        await session.delete(i)
                    map_res = await session.execute(select(SlackChannelMapping).where(SlackChannelMapping.organization_id == oid))
                    for m in map_res.scalars().all():
                        await session.delete(m)
                    await session.flush()
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

    print("\nAll Real Slack Users & Messages tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_slack_real_users_messages_flow())
