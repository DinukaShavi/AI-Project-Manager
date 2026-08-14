import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project, Repository
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_repository_linking_flow():
    print("Initializing GitHub Repository Linking validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Repo Link Org A {suffix}", domain=f"repolink-a-{suffix}.com")
                org_b = Organization(name=f"Repo Link Org B {suffix}", domain=f"repolink-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Repo Link Workspace A")
                session.add(workspace_a)
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Repo Link Project A")
                session.add(project_a)
                await session.commit()
                project_a_id = project_a.id
            print(f"Test orgs, workspace, and project created. Org A={org_a_id} Org B={org_b_id} Project A={project_a_id}")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            # 1. Linking a repository to a project in the caller's own org succeeds (201) and
            # returns the documented "Link confirmation object" (api_contract.md section 4.A).
            print("\nTest 1: Linking a repository to an owned project...")
            res = await client.post(
                "/api/v1/integrations/github/repositories",
                json={
                    "project_id": str(project_a_id),
                    "external_repo_id": "987654321",
                    "name": "backend-core",
                    "clone_url": "https://github.com/acme/backend-core.git",
                },
                headers=headers_a,
            )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            body = res.json()
            assert body["project_id"] == str(project_a_id)
            assert body["external_repo_id"] == "987654321"
            assert body["name"] == "backend-core"
            assert body["status"] == "linked"
            repo_id = body["id"]
            print(f"SUCCESS: Repository linked, id={repo_id}")

            # 2. The link must be a real, persisted row scoped to the correct organization.
            print("\nTest 2: Verifying the Repository row was actually persisted with the correct organization_id...")
            async with SessionLocal() as session:
                res_db = await session.execute(select(Repository).where(Repository.id == uuid.UUID(repo_id)))
                repo = res_db.scalar_one_or_none()
                assert repo is not None, "Repository row was not persisted"
                assert repo.organization_id == org_a_id
                assert repo.project_id == project_a_id
                assert repo.clone_url == "https://github.com/acme/backend-core.git"
            print("SUCCESS: Repository row persisted with correct tenant scoping.")

            # 3. Re-linking the same (project_id, external_repo_id) pair must update the
            # existing row in place, not silently accumulate duplicate link rows.
            print("\nTest 3: Verifying re-linking the same repo updates in place instead of duplicating...")
            res = await client.post(
                "/api/v1/integrations/github/repositories",
                json={
                    "project_id": str(project_a_id),
                    "external_repo_id": "987654321",
                    "name": "backend-core-renamed",
                    "clone_url": "https://github.com/acme/backend-core-renamed.git",
                },
                headers=headers_a,
            )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            assert res.json()["id"] == repo_id, "Re-linking should update the existing row, not create a new one"
            async with SessionLocal() as session:
                res_db = await session.execute(
                    select(Repository).where(Repository.project_id == project_a_id, Repository.external_repo_id == "987654321")
                )
                rows = res_db.scalars().all()
                assert len(rows) == 1, f"Expected exactly 1 row after re-link, found {len(rows)}"
                assert rows[0].name == "backend-core-renamed"
            print("SUCCESS: Re-linking updated the existing row in place; no duplicate rows created.")

            # 4. A user from a DIFFERENT organization must not be able to link a repository to
            # a project they don't own (cross-tenant isolation).
            print("\nTest 4: Verifying cross-tenant project access is rejected...")
            res = await client.post(
                "/api/v1/integrations/github/repositories",
                json={
                    "project_id": str(project_a_id),
                    "external_repo_id": "111222333",
                    "name": "cross-tenant-attempt",
                    "clone_url": "https://github.com/acme/cross-tenant-attempt.git",
                },
                headers=headers_b,
            )
            assert res.status_code == 404, f"Expected 404 for cross-tenant project access, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant repository linking correctly rejected with 404.")

            # 5. Linking to a nonexistent project must 404, not 500.
            print("\nTest 5: Verifying a nonexistent project_id returns 404...")
            res = await client.post(
                "/api/v1/integrations/github/repositories",
                json={
                    "project_id": str(uuid.uuid4()),
                    "external_repo_id": "444555666",
                    "name": "ghost-project-repo",
                    "clone_url": "https://github.com/acme/ghost-project-repo.git",
                },
                headers=headers_a,
            )
            assert res.status_code == 404, f"Expected 404 for nonexistent project, got {res.status_code}: {res.text}"
            print("SUCCESS: Nonexistent project_id correctly returns 404.")

        finally:
            print("\nCleaning up repository linking test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    if project_a_id:
                        repo_res = await session.execute(select(Repository).where(Repository.project_id == project_a_id))
                        for r in repo_res.scalars().all():
                            await session.delete(r)
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

    print("\nAll GitHub Repository Linking tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_repository_linking_flow())
