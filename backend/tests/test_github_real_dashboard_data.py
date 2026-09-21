import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

import app.db.base  # Register models
from app.main import app
from app.core.security import encrypt_token
from app.models.tenant import Organization, Workspace
from app.models.project import Project, Repository
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

_real_get = httpx.AsyncClient.get
REPO_A = "acme/repo-a"


async def _fake_github_get(self, url, **kwargs):
    url_s = str(url)
    if url_s == f"https://api.github.com/repos/{REPO_A}/pulls":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json=[
            {
                "id": 7001, "number": 12, "title": "Fix login race condition", "state": "open",
                "user": {"login": "octo-dev"}, "html_url": f"https://github.com/{REPO_A}/pull/12",
                "created_at": "2026-08-01T00:00:00Z", "draft": False, "additions": 40, "deletions": 5,
                "labels": [{"name": "bug"}], "merged_at": None,
            },
        ])
    if url_s == f"https://api.github.com/repos/{REPO_A}/commits":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json=[
            {
                "sha": "abc123def456abc123def456abc123def456abc",
                "commit": {"message": "fix: race condition on login", "author": {"name": "Octo Dev", "email": "octo@example.com", "date": "2026-08-01T00:00:00Z"}},
                "html_url": f"https://github.com/{REPO_A}/commit/abc123",
            },
        ])
    if url_s == f"https://api.github.com/repos/{REPO_A}/issues":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json=[
            {
                "id": 8001, "number": 5, "title": "Crash on save", "state": "open",
                "user": {"login": "octo-dev"}, "html_url": f"https://github.com/{REPO_A}/issues/5",
                "created_at": "2026-07-30T00:00:00Z", "comments": 2, "labels": ["crash"],
            },
            {
                # A pull request returned by GitHub's /issues endpoint -- must be filtered out.
                "id": 7001, "number": 12, "title": "Fix login race condition", "state": "open",
                "user": {"login": "octo-dev"}, "html_url": f"https://github.com/{REPO_A}/pull/12",
                "created_at": "2026-08-01T00:00:00Z", "comments": 0, "labels": [],
                "pull_request": {"url": f"https://api.github.com/repos/{REPO_A}/pulls/12"},
            },
        ])
    return await _real_get(self, url, **kwargs)


async def test_github_real_dashboard_data_flow():
    print("Initializing Real GitHub Dashboard Data (Phase 61) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None
    project_a2_id = None
    project_b_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"GH Dash Org A {suffix}", domain=f"ghdash-a-{suffix}.com")
                org_b = Organization(name=f"GH Dash Org B {suffix}", domain=f"ghdash-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="GH Dash Workspace A")
                workspace_b = Workspace(organization_id=org_b_id, name="GH Dash Workspace B")
                session.add_all([workspace_a, workspace_b])
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="GH Dash Project A (has linked repo)")
                project_a2 = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="GH Dash Project A2 (no linked repos)")
                project_b = Project(organization_id=org_b_id, workspace_id=workspace_b.id, name="GH Dash Project B (not connected)")
                session.add_all([project_a, project_a2, project_b])
                await session.flush()
                project_a_id, project_a2_id, project_b_id = project_a.id, project_a2.id, project_b.id

                repo = Repository(organization_id=org_a_id, project_id=project_a_id, external_repo_id="9001", name=REPO_A, clone_url=f"https://github.com/{REPO_A}.git")
                session.add(repo)
                await session.flush()

                integration_a = Integration(organization_id=org_a_id, provider="github", is_active=True)
                session.add(integration_a)
                await session.flush()
                token_a = OAuthToken(organization_id=org_a_id, integration_id=integration_a.id, encrypted_access_token=encrypt_token("fake-github-access-token"), scopes=["repo"])
                session.add(token_a)
                await session.commit()
            print(f"Test orgs/projects created. Org A={org_a_id} (GitHub connected, repo linked to Project A) Org B={org_b_id} (not connected)")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            with patch.object(httpx.AsyncClient, "get", new=_fake_github_get):
                # 1. Real pull requests for a project with a linked, connected repo.
                print("\nTest 1: Verifying real pull request data is returned...")
                res = await client.get(f"/api/v1/integrations/github/pull-requests?project_id={project_a_id}", headers=headers_a)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
                body = res.json()
                assert body["total_pull_requests"] == 1
                assert body["pull_requests"][0]["title"] == "Fix login race condition"
                assert body["pull_requests"][0]["repository"] == REPO_A
                print("SUCCESS: Real pull request data correctly returned.")

                # 2. Real commits.
                print("\nTest 2: Verifying real commit data is returned...")
                res = await client.get(f"/api/v1/integrations/github/commits?project_id={project_a_id}", headers=headers_a)
                assert res.status_code == 200, res.text
                body = res.json()
                assert body["total_commits"] == 1
                assert body["commits"][0]["message"] == "fix: race condition on login"
                assert body["commits"][0]["short_sha"] == "abc123d"
                print("SUCCESS: Real commit data correctly returned.")

                # 3. Real issues, with PR items correctly filtered out of the response.
                print("\nTest 3: Verifying real issue data is returned with PR items filtered out...")
                res = await client.get(f"/api/v1/integrations/github/issues?project_id={project_a_id}", headers=headers_a)
                assert res.status_code == 200, res.text
                body = res.json()
                assert body["total_issues"] == 1, f"Expected the PR-shaped item to be filtered out, got {body['total_issues']}"
                assert body["issues"][0]["title"] == "Crash on save"
                print("SUCCESS: Real issue data correctly returned, PR items filtered out.")

                # 4. A project with zero linked repos returns an empty (not error) result.
                print("\nTest 4: Verifying a project with no linked repos returns an empty result...")
                res = await client.get(f"/api/v1/integrations/github/pull-requests?project_id={project_a2_id}", headers=headers_a)
                assert res.status_code == 200, res.text
                assert res.json()["total_pull_requests"] == 0
                print("SUCCESS: No-linked-repos project correctly returned an empty result, not an error.")

                # 5. repository naming a repo not linked to the project -> 404.
                print("\nTest 5: Verifying an unlinked repository name returns 404...")
                res = await client.get(f"/api/v1/integrations/github/pull-requests?project_id={project_a_id}&repository=acme/not-linked", headers=headers_a)
                assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
                print("SUCCESS: Unlinked repository name correctly returns 404.")

            # 6. GitHub not connected for the org -> 400, no crash.
            print("\nTest 6: Verifying a not-connected organization gets a 400...")
            res = await client.get(f"/api/v1/integrations/github/pull-requests?project_id={project_b_id}", headers=headers_b)
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Not-connected organization correctly rejected with 400.")

            # 7. Cross-tenant: Org B cannot read Org A's project's real GitHub data.
            print("\nTest 7: Verifying cross-tenant isolation...")
            res = await client.get(f"/api/v1/integrations/github/pull-requests?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant access correctly rejected (404).")

        finally:
            print("\nCleaning up test database entries...")
            async with SessionLocal() as session:
                from app.models.tenant import User
                from sqlalchemy import select
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    for model in [OAuthToken]:
                        res_db = await session.execute(select(model).where(model.organization_id == oid))
                        for row in res_db.scalars().all():
                            await session.delete(row)
                    await session.flush()
                    int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                    for i in int_res.scalars().all():
                        await session.delete(i)
                    repo_res = await session.execute(select(Repository).where(Repository.organization_id == oid))
                    for r in repo_res.scalars().all():
                        await session.delete(r)
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

    print("\nAll Real GitHub Dashboard Data tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_github_real_dashboard_data_flow())
