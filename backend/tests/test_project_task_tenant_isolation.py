import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project, ProjectTask
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_project_task_tenant_isolation_flow():
    print("Initializing Project/Task Cross-Tenant Isolation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    ws_a_id = None
    project_a_id = None
    task_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Tenant Isolation Org A {suffix}", domain=f"tiso-a-{suffix}.com")
                org_b = Organization(name=f"Tenant Isolation Org B {suffix}", domain=f"tiso-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.commit()
            org_a_id, org_b_id = org_a.id, org_b.id
            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs and authenticated users created. Org A={org_a_id} Org B={org_b_id}")

            # Org A creates a real workspace/project/task via the API (happy path, and the
            # fixtures the isolation checks below target).
            res = await client.post("/api/v1/workspaces", json={"name": "Org A Workspace"}, headers=headers_a)
            assert res.status_code == 201, res.text
            ws_a_id = res.json()["workspace_id"]

            res = await client.post(
                "/api/v1/projects",
                json={"workspace_id": ws_a_id, "name": "Org A Project"},
                headers=headers_a,
            )
            assert res.status_code == 201, res.text
            project_a_id = res.json()["project_id"]

            res = await client.post(
                "/api/v1/tasks",
                json={"project_id": project_a_id, "title": "Org A Task"},
                headers=headers_a,
            )
            assert res.status_code == 201, res.text
            task_a_id = res.json()["task_id"]
            print("SUCCESS: Org A created its own workspace, project, and task via the API (happy path).")

            # 1. Org B must not be able to create a project inside Org A's workspace.
            print("\nTest 1: Verifying Org B cannot create a project under Org A's workspace...")
            res = await client.post(
                "/api/v1/projects",
                json={"workspace_id": ws_a_id, "name": "Hostile Cross-Tenant Project"},
                headers=headers_b,
            )
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) when targeting Org A's workspace.")

            # 2. Org B must not be able to list Org A's workspace's projects.
            print("\nTest 2: Verifying Org B cannot list Org A's workspace's projects...")
            res = await client.get(f"/api/v1/projects?workspace_id={ws_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) when listing Org A's workspace's projects.")

            # 3. Org B must not be able to fetch Org A's project by ID (not merely
            # filtered out of a list -- direct ID lookup must also be rejected).
            print("\nTest 3: Verifying Org B cannot fetch Org A's project by ID...")
            res = await client.get(f"/api/v1/projects/{project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) when fetching Org A's project directly.")

            # 4. Org B must not be able to create a task under Org A's project.
            print("\nTest 4: Verifying Org B cannot create a task under Org A's project...")
            res = await client.post(
                "/api/v1/tasks",
                json={"project_id": project_a_id, "title": "Hostile Cross-Tenant Task"},
                headers=headers_b,
            )
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) when creating a task under Org A's project.")

            # 5. Org B must not be able to list Org A's project's tasks.
            print("\nTest 5: Verifying Org B cannot list Org A's project's tasks...")
            res = await client.get(f"/api/v1/tasks?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) when listing Org A's project's tasks.")

            # 6. Org B must not be able to mutate Org A's task by ID.
            print("\nTest 6: Verifying Org B cannot update Org A's task...")
            res = await client.put(f"/api/v1/tasks/{task_a_id}", json={"status": "done"}, headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            async with SessionLocal() as session:
                unchanged = await session.get(ProjectTask, uuid.UUID(task_a_id))
                assert unchanged.status != "done", "Org B's rejected update must not have mutated Org A's task"
            print("SUCCESS: Org B correctly rejected (404) when updating Org A's task; task left unmodified.")

            # 7. Org A must still be able to fully manage its own resources after the fix
            # (regression check -- the isolation fix must not break legitimate same-org access).
            print("\nTest 7: Verifying Org A retains full access to its own resources...")
            res = await client.get(f"/api/v1/projects/{project_a_id}", headers=headers_a)
            assert res.status_code == 200
            res = await client.get(f"/api/v1/tasks?project_id={project_a_id}", headers=headers_a)
            assert res.status_code == 200 and res.json()["tasks_count"] == 1
            res = await client.put(f"/api/v1/tasks/{task_a_id}", json={"status": "done"}, headers=headers_a)
            assert res.status_code == 200 and res.json()["status"] == "done"
            print("SUCCESS: Org A retains full, correct access to its own workspace/project/task.")

        finally:
            print("\nCleaning up tenant isolation test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    task_res = await session.execute(select(ProjectTask).where(ProjectTask.organization_id == oid))
                    for t in task_res.scalars().all():
                        await session.delete(t)
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

    print("\nAll Project/Task Cross-Tenant Isolation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_project_task_tenant_isolation_flow())
