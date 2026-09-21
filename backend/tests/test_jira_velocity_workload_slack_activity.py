import asyncio
import uuid
from datetime import datetime, timezone
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
CLOUD_ID = "cloud-site-id-jira72"
PROJECT_KEY = "JD72"
CHANNEL_ID = "C0SLACK72"

TS1 = datetime(2026, 6, 1, 6, 46, 40, tzinfo=timezone.utc).timestamp()
TS2 = datetime(2026, 6, 1, 8, 15, 0, tzinfo=timezone.utc).timestamp()
TS3 = datetime(2026, 6, 1, 8, 45, 0, tzinfo=timezone.utc).timestamp()


async def _fake_jira_get(self, url, **kwargs):
    url_s = str(url)
    base = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}"
    if url_s == f"{base}/rest/api/3/field":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json=[{"id": "customfield_10099", "name": "Story Points"}])
    if url_s == f"{base}/rest/api/3/search":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"issues": [
            {"id": "1", "key": f"{PROJECT_KEY}-1", "fields": {"summary": "A", "status": {"name": "Open"}, "priority": {"name": "High"}, "assignee": {"displayName": "Alice"}, "customfield_10099": 5}},
            {"id": "2", "key": f"{PROJECT_KEY}-2", "fields": {"summary": "B", "status": {"name": "Open"}, "priority": {"name": "High"}, "assignee": {"displayName": "Alice"}, "customfield_10099": 3}},
            {"id": "3", "key": f"{PROJECT_KEY}-3", "fields": {"summary": "C", "status": {"name": "Open"}, "priority": {"name": "Low"}, "assignee": {"displayName": "Bob"}, "customfield_10099": 2}},
        ]})
    if url_s == f"{base}/rest/agile/1.0/board":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"values": [{"id": 701, "name": f"{PROJECT_KEY} board"}]})
    if url_s == f"{base}/rest/agile/1.0/board/701/sprint":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"values": [
            {"id": 801, "name": "Sprint 1", "state": "closed", "startDate": "2026-06-01T00:00:00Z", "endDate": "2026-06-15T00:00:00Z"},
            {"id": 802, "name": "Sprint 2", "state": "closed", "startDate": "2026-06-16T00:00:00Z", "endDate": "2026-06-30T00:00:00Z"},
            {"id": 803, "name": "Sprint 3", "state": "active", "startDate": "2026-07-01T00:00:00Z", "endDate": None},
        ]})
    if url_s == f"{base}/rest/agile/1.0/sprint/801/issue":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"issues": [
            {"fields": {"customfield_10099": 5, "status": {"statusCategory": {"key": "done"}}}},
            {"fields": {"customfield_10099": 3, "status": {"statusCategory": {"key": "indeterminate"}}}},
        ]})
    if url_s == f"{base}/rest/agile/1.0/sprint/802/issue":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"issues": [
            {"fields": {"customfield_10099": 6, "status": {"statusCategory": {"key": "done"}}}},
            {"fields": {"customfield_10099": 2, "status": {"statusCategory": {"key": "done"}}}},
        ]})
    if url_s == f"{base}/rest/agile/1.0/sprint/803/issue":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"issues": []})
    return await _real_get(self, url, **kwargs)


async def _fake_slack_get(self, url, **kwargs):
    url_s = str(url)
    if url_s == "https://slack.com/api/users.list":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"ok": True, "members": [
            {"id": "U100", "name": "alice", "is_bot": False, "deleted": False, "profile": {"real_name": "Alice Smith"}},
        ]})
    if url_s == "https://slack.com/api/conversations.history":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"ok": True, "messages": [
            {"ts": str(TS1), "user": "U100", "text": "Good morning team"},
            {"ts": str(TS2), "user": "U100", "text": "Standup starting now"},
            {"ts": str(TS3), "user": "U100", "text": "Wrapping up the sprint review"},
        ]})
    return await _real_get(self, url, **kwargs)


async def test_jira_velocity_workload_slack_activity_flow():
    print("Initializing Real Jira Workload/Velocity & Slack Activity (Phase 72) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"NLP Cluster Org A {suffix}", domain=f"nlp-a-{suffix}.com")
                org_b = Organization(name=f"NLP Cluster Org B {suffix}", domain=f"nlp-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="NLP Cluster Workspace A")
                session.add(workspace_a)
                await session.flush()
                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="NLP Cluster Project A", jira_project_key=PROJECT_KEY)
                session.add(project_a)
                await session.flush()
                project_a_id = project_a.id

                mapping = SlackChannelMapping(organization_id=org_a_id, project_id=project_a_id, slack_channel_id=CHANNEL_ID)
                session.add(mapping)

                jira_integration = Integration(organization_id=org_a_id, provider="jira", is_active=True, external_workspace_id=CLOUD_ID)
                slack_integration = Integration(organization_id=org_a_id, provider="slack", is_active=True)
                session.add_all([jira_integration, slack_integration])
                await session.flush()
                jira_token = OAuthToken(organization_id=org_a_id, integration_id=jira_integration.id, encrypted_access_token=encrypt_token("fake-jira-token"), scopes=["read:jira-work"])
                slack_token = OAuthToken(organization_id=org_a_id, integration_id=slack_integration.id, encrypted_access_token=encrypt_token("fake-slack-token"), scopes=["users:read", "channels:history"])
                session.add_all([jira_token, slack_token])
                await session.commit()
            print(f"Test org/project created. Org A={org_a_id} Project={project_a_id}")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            with patch.object(httpx.AsyncClient, "get", new=_fake_jira_get):
                # 1. Real per-assignee workload aggregated from real issue data.
                print("\nTest 1: Verifying real Jira workload is aggregated correctly...")
                res = await client.get(f"/api/v1/integrations/jira/workload?project_id={project_a_id}", headers=headers_a)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
                workload = {w["assignee"]: w for w in res.json()["team_workload"]}
                assert workload["Alice"]["assigned_issues"] == 2
                assert workload["Alice"]["total_story_points"] == 8
                assert workload["Alice"]["percentage_of_team_points"] == 80.0
                assert workload["Bob"]["assigned_issues"] == 1
                assert workload["Bob"]["total_story_points"] == 2
                assert workload["Bob"]["percentage_of_team_points"] == 20.0
                assert "capacity_percentage" not in workload["Alice"], "Fabricated capacity_percentage must not be present"
                print("SUCCESS: Real Jira workload correctly aggregated with relative point shares.")

                # 2. Real velocity reconstructed from real per-sprint story points; active
                #    sprint excluded.
                print("\nTest 2: Verifying real Jira velocity is reconstructed correctly, excluding the active sprint...")
                res = await client.get(f"/api/v1/integrations/jira/velocity?project_id={project_a_id}", headers=headers_a)
                assert res.status_code == 200, res.text
                body = res.json()
                assert len(body["sprint_velocity_history"]) == 2, "Active sprint must be excluded from velocity history"
                assert body["sprint_velocity_history"][0] == {"sprint": "Sprint 1", "committed": 8.0, "completed": 5.0}
                assert body["sprint_velocity_history"][1] == {"sprint": "Sprint 2", "committed": 8.0, "completed": 8.0}
                assert body["average_velocity"] == 6.5
                print("SUCCESS: Real Jira velocity correctly reconstructed from real per-sprint data.")

            with patch.object(httpx.AsyncClient, "get", new=_fake_slack_get):
                # 3. Real activity_by_hour/message_count computed deterministically from real
                #    message timestamps; sentiment/topics honestly None/[] in this key-less
                #    environment rather than the old fabricated fixed numbers.
                print("\nTest 3: Verifying real Slack activity is computed correctly, with honest sentiment fallback...")
                res = await client.get(f"/api/v1/integrations/slack/activity?channel_id={CHANNEL_ID}", headers=headers_a)
                assert res.status_code == 200, res.text
                body = res.json()
                assert body["message_count"] == 3
                by_hour = {b["hour"]: b["messages"] for b in body["activity_by_hour"]}
                assert by_hour == {"06:00": 1, "08:00": 2}
                assert body["sentiment_score"] is None, "No LLM configured in this environment -- must be honest None, not a fabricated number"
                assert body["top_discussed_topics"] == []
                print("SUCCESS: Real Slack activity correctly computed with honest sentiment fallback.")

                # 4. An unmapped channel_id -> 404.
                print("\nTest 4: Verifying an unmapped channel_id returns 404...")
                res = await client.get("/api/v1/integrations/slack/activity?channel_id=C0NOTMAPPED", headers=headers_a)
                assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
                print("SUCCESS: Unmapped channel_id correctly returns 404.")

            # 5. Unauthenticated request rejected on all three routes.
            print("\nTest 5: Verifying unauthenticated requests are rejected...")
            for path in (
                f"/api/v1/integrations/jira/workload?project_id={project_a_id}",
                f"/api/v1/integrations/jira/velocity?project_id={project_a_id}",
                f"/api/v1/integrations/slack/activity?channel_id={CHANNEL_ID}",
            ):
                res = await client.get(path)
                assert res.status_code in (401, 403), f"Expected 401/403 for {path}, got {res.status_code}"
            print("SUCCESS: All three routes correctly reject unauthenticated requests.")

            # 6. Cross-tenant isolation on all three routes.
            print("\nTest 6: Verifying cross-tenant isolation...")
            res = await client.get(f"/api/v1/integrations/jira/workload?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            res = await client.get(f"/api/v1/integrations/jira/velocity?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            res = await client.get(f"/api/v1/integrations/slack/activity?channel_id={CHANNEL_ID}", headers=headers_b)
            assert res.status_code == 400, f"Expected 400 (Org B has no Slack connection), got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant access correctly rejected on all three routes.")

        finally:
            print("\nCleaning up test database entries...")
            async with SessionLocal() as session:
                from app.models.tenant import User
                from sqlalchemy import select
                for oid in [o for o in [org_a_id, org_b_id] if o]:
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

    print("\nAll Real Jira Workload/Velocity & Slack Activity tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_jira_velocity_workload_slack_activity_flow())
