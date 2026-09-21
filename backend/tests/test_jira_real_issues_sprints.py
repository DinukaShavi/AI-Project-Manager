import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

import app.db.base  # Register models
from app.main import app
from app.core.security import encrypt_token
from app.models.tenant import Organization, Workspace
from app.models.project import Project
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

_real_get = httpx.AsyncClient.get
CLOUD_ID = "cloud-site-id-jira62"
PROJECT_KEY = "JD62"


async def _fake_jira_get(self, url, **kwargs):
    url_s = str(url)
    base = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}"
    if url_s == f"{base}/rest/api/3/field":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json=[
            {"id": "customfield_10099", "name": "Story Points"},
            {"id": "summary", "name": "Summary"},
        ])
    if url_s == f"{base}/rest/api/3/search":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"issues": [
            {
                "id": "30001", "key": f"{PROJECT_KEY}-1",
                "fields": {
                    "summary": "Fix login bug", "status": {"name": "In Progress"}, "priority": {"name": "High"},
                    "assignee": {"displayName": "Alice Smith"}, "customfield_10099": 5,
                },
            },
        ]})
    if url_s == f"{base}/rest/agile/1.0/board":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"values": [{"id": 401, "name": f"{PROJECT_KEY} board"}]})
    if url_s == f"{base}/rest/agile/1.0/board/401/sprint":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"values": [
            {"id": 501, "name": "Sprint 1", "state": "active", "startDate": "2026-08-01T00:00:00Z", "endDate": "2026-08-15T00:00:00Z"},
        ]})
    if url_s == f"{base}/rest/agile/1.0/sprint/501/issue":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"issues": [
            {"fields": {"customfield_10099": 5, "status": {"statusCategory": {"key": "done"}}}},
            {"fields": {"customfield_10099": 3, "status": {"statusCategory": {"key": "indeterminate"}}}},
        ]})
    return await _real_get(self, url, **kwargs)


async def test_jira_real_issues_sprints_flow():
    print("Initializing Real Jira Issues & Sprints (Phase 62) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None
    project_a_no_key_id = None
    project_b_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Jira Dash Org A {suffix}", domain=f"jiradash-a-{suffix}.com")
                org_b = Organization(name=f"Jira Dash Org B {suffix}", domain=f"jiradash-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Jira Dash Workspace A")
                workspace_b = Workspace(organization_id=org_b_id, name="Jira Dash Workspace B")
                session.add_all([workspace_a, workspace_b])
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Jira Dash Project A", jira_project_key=PROJECT_KEY)
                project_a_no_key = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Jira Dash Project A (no key)")
                project_b = Project(organization_id=org_b_id, workspace_id=workspace_b.id, name="Jira Dash Project B (not connected)")
                session.add_all([project_a, project_a_no_key, project_b])
                await session.flush()
                project_a_id, project_a_no_key_id, project_b_id = project_a.id, project_a_no_key.id, project_b.id

                integration_a = Integration(organization_id=org_a_id, provider="jira", is_active=True, external_workspace_id=CLOUD_ID)
                session.add(integration_a)
                await session.flush()
                token_a = OAuthToken(organization_id=org_a_id, integration_id=integration_a.id, encrypted_access_token=encrypt_token("fake-jira-access-token"), scopes=["read:jira-work"])
                session.add(token_a)
                await session.commit()
            print(f"Test orgs/projects created. Org A={org_a_id} (Jira connected, cloud_id={CLOUD_ID}) Org B={org_b_id} (not connected)")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            with patch.object(httpx.AsyncClient, "get", new=_fake_jira_get):
                # 1. Real issues, with a best-effort-resolved story points value.
                print("\nTest 1: Verifying real Jira issue data is returned with story points resolved...")
                res = await client.get(f"/api/v1/integrations/jira/issues?project_id={project_a_id}", headers=headers_a)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
                body = res.json()
                assert body["total_issues"] == 1
                issue = body["issues"][0]
                assert issue["key"] == f"{PROJECT_KEY}-1"
                assert issue["summary"] == "Fix login bug"
                assert issue["assignee"] == "Alice Smith"
                assert issue["story_points"] == 5
                print("SUCCESS: Real Jira issue data correctly returned with resolved story points.")

                # 2. Real sprints, with per-sprint story points aggregated from real issues.
                print("\nTest 2: Verifying real Jira sprint data is returned with aggregated story points...")
                res = await client.get(f"/api/v1/integrations/jira/sprints?project_id={project_a_id}", headers=headers_a)
                assert res.status_code == 200, res.text
                body = res.json()
                assert body["total_sprints"] == 1
                sprint = body["sprints"][0]
                assert sprint["name"] == "Sprint 1"
                assert sprint["completed_story_points"] == 5.0
                assert sprint["total_story_points"] == 8.0
                print("SUCCESS: Real Jira sprint data correctly returned with aggregated story points.")

            # 3. Story points field unresolvable -> null, not a fabricated 0.
            print("\nTest 3: Verifying unresolvable story points fields return null, not 0...")
            async def _fake_jira_get_no_field(self, url, **kwargs):
                url_s = str(url)
                base = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}"
                if url_s == f"{base}/rest/api/3/field":
                    req = httpx.Request("GET", url_s)
                    return httpx.Response(200, request=req, json=[{"id": "summary", "name": "Summary"}])
                if url_s == f"{base}/rest/api/3/search":
                    req = httpx.Request("GET", url_s)
                    return httpx.Response(200, request=req, json={"issues": [
                        {"id": "30002", "key": f"{PROJECT_KEY}-2", "fields": {"summary": "No points field", "status": {"name": "Open"}, "priority": {"name": "Low"}, "assignee": None}},
                    ]})
                return await _real_get(self, url, **kwargs)

            with patch.object(httpx.AsyncClient, "get", new=_fake_jira_get_no_field):
                res = await client.get(f"/api/v1/integrations/jira/issues?project_id={project_a_id}", headers=headers_a)
                assert res.status_code == 200, res.text
                assert res.json()["issues"][0]["story_points"] is None, "Unresolvable story points must be null, not a fabricated 0"
            print("SUCCESS: Unresolvable story points field correctly returned null.")

            # 4. Jira not connected for the org -> 400.
            print("\nTest 4: Verifying a not-connected organization gets a 400...")
            res = await client.get(f"/api/v1/integrations/jira/issues?project_id={project_b_id}", headers=headers_b)
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Not-connected organization correctly rejected with 400.")

            # 5. Project with no jira_project_key configured -> 404.
            print("\nTest 5: Verifying a project with no jira_project_key returns 404...")
            res = await client.get(f"/api/v1/integrations/jira/issues?project_id={project_a_no_key_id}", headers=headers_a)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Project with no Jira key correctly returns 404.")

            # 6. Cross-tenant isolation.
            print("\nTest 6: Verifying cross-tenant isolation...")
            res = await client.get(f"/api/v1/integrations/jira/issues?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant access correctly rejected (404).")

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

    print("\nAll Real Jira Issues & Sprints tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_jira_real_issues_sprints_flow())
