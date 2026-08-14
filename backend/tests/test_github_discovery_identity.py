import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.models.tenant import Organization, Workspace
from app.models.project import Project
from app.db.session import SessionLocal
from sqlalchemy import select
from app.models.tenant import User
from app.models.project import Repository
from tests._auth_helpers import create_authenticated_headers


_real_post = httpx.AsyncClient.post
_real_get = httpx.AsyncClient.get
GITHUB_EXTERNAL_USER_ID = 999888777
GITHUB_LOGIN = "octo-demo-dev"


async def _fake_github_post(self, url, **kwargs):
    if "github.com/login/oauth/access_token" in str(url):
        req = httpx.Request("POST", str(url))
        return httpx.Response(200, request=req, json={"access_token": "gho_mocked_discovery_token", "token_type": "bearer", "scope": "repo,user"})
    return await _real_post(self, url, **kwargs)


async def _fake_github_get(self, url, **kwargs):
    if str(url) == "https://api.github.com/user":
        req = httpx.Request("GET", str(url))
        return httpx.Response(200, request=req, json={"id": GITHUB_EXTERNAL_USER_ID, "login": GITHUB_LOGIN})
    if str(url) == "https://api.github.com/user/repos":
        req = httpx.Request("GET", str(url))
        return httpx.Response(200, request=req, json=[
            {"id": 5001, "full_name": "acme-org/backend-core", "clone_url": "https://github.com/acme-org/backend-core.git", "private": True, "default_branch": "main", "updated_at": "2026-08-01T00:00:00Z"},
            {"id": 5002, "full_name": "acme-org/frontend-app", "clone_url": "https://github.com/acme-org/frontend-app.git", "private": False, "default_branch": "main", "updated_at": "2026-08-02T00:00:00Z"},
        ])
    return await _real_get(self, url, **kwargs)


async def test_github_discovery_identity_flow():
    print("Initializing GitHub Repository Discovery & Identity validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    original_creds = (settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET)
    settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET = "test_gh_client_id", "test_gh_client_secret"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"GH Discover Org A {suffix}", domain=f"ghdisc-a-{suffix}.com")
                org_b = Organization(name=f"GH Discover Org B {suffix}", domain=f"ghdisc-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="GH Discover Workspace A")
                session.add(workspace_a)
                await session.flush()
                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="GH Discover Project A")
                session.add(project_a)
                await session.commit()
                project_a_id = project_a.id

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            with patch.object(httpx.AsyncClient, "post", new=_fake_github_post), patch.object(httpx.AsyncClient, "get", new=_fake_github_get):
                # 1. Connecting GitHub auto-links the connecting user's real GitHub identity.
                print("\nTest 1: Verifying GitHub OAuth connect resolves and links a real identity...")
                res = await client.get("/api/v1/integrations/oauth/github/callback?code=fake_gh_code", headers=headers_a)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

                res = await client.get("/api/v1/organizations/external-identities/me", headers=headers_a)
                assert res.status_code == 200
                gh_identity = next((i for i in res.json()["identities"] if i["provider"] == "github"), None)
                assert gh_identity is not None, "Expected a real auto-created GitHub identity"
                assert gh_identity["external_account_id"] == str(GITHUB_EXTERNAL_USER_ID)
                assert gh_identity["external_display_name"] == GITHUB_LOGIN
                print(f"SUCCESS: Real GitHub identity linked: {GITHUB_LOGIN} ({GITHUB_EXTERNAL_USER_ID}).")

                # 2. Discovery returns real repos from the connected token.
                print("\nTest 2: Verifying repository discovery returns real repositories...")
                res = await client.get("/api/v1/integrations/github/discover-repositories", headers=headers_a)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
                discovered = res.json()["repositories"]
                assert len(discovered) == 2
                assert {"external_repo_id": "5001", "name": "acme-org/backend-core", "clone_url": "https://github.com/acme-org/backend-core.git", "private": True, "default_branch": "main", "updated_at": "2026-08-01T00:00:00Z"} in discovered
                print(f"SUCCESS: Discovered {len(discovered)} real repositories from the connected GitHub token.")

            # 3. Discovery without a GitHub connection returns a clean 400.
            print("\nTest 3: Verifying discovery fails cleanly for an org with no GitHub connection...")
            res = await client.get("/api/v1/integrations/github/discover-repositories", headers=headers_b)
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Not-connected organization correctly rejected with 400.")

            # 4. Link a discovered repo, then read it back via the real linked-repositories list.
            print("\nTest 4: Linking a discovered repository, then reading it back...")
            res = await client.post(
                "/api/v1/integrations/github/repositories",
                json={"project_id": str(project_a_id), "external_repo_id": "5001", "name": "acme-org/backend-core", "clone_url": "https://github.com/acme-org/backend-core.git"},
                headers=headers_a,
            )
            assert res.status_code == 201, res.text

            res = await client.get(f"/api/v1/integrations/github/linked-repositories?project_id={project_a_id}", headers=headers_a)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            linked = res.json()["repositories"]
            assert len(linked) == 1
            assert linked[0]["external_repo_id"] == "5001"
            print("SUCCESS: Linked repository correctly appears in the real linked-repositories list.")

            # 5. Cross-tenant: Org B cannot read Org A's linked repositories.
            print("\nTest 5: Verifying cross-tenant isolation on linked-repositories...")
            res = await client.get(f"/api/v1/integrations/github/linked-repositories?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant linked-repositories access correctly rejected (404).")

            # 6. A nonexistent project_id returns 404, not a crash.
            print("\nTest 6: Verifying a nonexistent project_id returns 404...")
            res = await client.get(f"/api/v1/integrations/github/linked-repositories?project_id={uuid.uuid4()}", headers=headers_a)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Nonexistent project_id correctly returns 404.")

        finally:
            print("\nCleaning up GitHub discovery/identity test database entries...")
            settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET = original_creds
            async with SessionLocal() as session:
                from app.models.external_identity import ExternalIdentity
                from app.models.integration import Integration, OAuthToken
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    if project_a_id:
                        repo_res = await session.execute(select(Repository).where(Repository.project_id == project_a_id))
                        for r in repo_res.scalars().all():
                            await session.delete(r)
                    for model in [ExternalIdentity, OAuthToken]:
                        res_db = await session.execute(select(model).where(model.organization_id == oid))
                        for row in res_db.scalars().all():
                            await session.delete(row)
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

    print("\nAll GitHub Repository Discovery & Identity tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_github_discovery_identity_flow())
