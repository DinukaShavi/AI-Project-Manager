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


async def test_analytics_tenant_isolation_flow():
    print("Initializing Analytics Cross-Tenant Isolation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Analytics Tenant Org A {suffix}", domain=f"atiso-a-{suffix}.com")
                org_b = Organization(name=f"Analytics Tenant Org B {suffix}", domain=f"atiso-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Analytics Workspace A")
                session.add(workspace_a)
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Analytics Project A")
                session.add(project_a)
                await session.flush()
                project_a_id = project_a.id

                task = ProjectTask(organization_id=org_a_id, project_id=project_a_id, title="Org A Sprint Task", status="done", priority="high", story_points=5)
                session.add(task)
                await session.commit()

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs, project, and task created. Org A={org_a_id} Org B={org_b_id} Project A={project_a_id}")

            # 1. Org A can read its own project's real sprint analytics.
            print("\nTest 1: Verifying Org A can read its own project's sprint analytics...")
            res = await client.get(f"/api/v1/analytics/sprint?project_id={project_a_id}", headers=headers_a)
            assert res.status_code == 200, res.text
            assert res.json()["total_tasks"] == 1
            print("SUCCESS: Org A retrieved its own real sprint analytics.")

            # 2. Org B must NOT be able to read Org A's sprint analytics by project_id.
            print("\nTest 2: Verifying Org B cannot read Org A's sprint analytics...")
            res = await client.get(f"/api/v1/analytics/sprint?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) reading Org A's sprint analytics.")

            # 3. Org B must NOT be able to read Org A's burndown chart.
            print("\nTest 3: Verifying Org B cannot read Org A's burndown chart...")
            res = await client.get(f"/api/v1/analytics/burndown?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) reading Org A's burndown chart.")

            # 4. Org B must NOT be able to read Org A's completion forecast.
            print("\nTest 4: Verifying Org B cannot read Org A's completion forecast...")
            res = await client.get(f"/api/v1/analytics/predict-completion?project_id={project_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Org B correctly rejected (404) reading Org A's completion forecast.")

            # 5. Org A's own burndown/forecast endpoints still work correctly (regression guard).
            print("\nTest 5: Verifying Org A's own burndown/forecast endpoints still work...")
            res = await client.get(f"/api/v1/analytics/burndown?project_id={project_a_id}", headers=headers_a)
            assert res.status_code == 200, res.text
            res = await client.get(f"/api/v1/analytics/predict-completion?project_id={project_a_id}", headers=headers_a)
            assert res.status_code == 200, res.text
            print("SUCCESS: Org A retains full working access to its own analytics endpoints.")

        finally:
            print("\nCleaning up analytics tenant isolation test database entries...")
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

    print("\nAll Analytics Cross-Tenant Isolation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_analytics_tenant_isolation_flow())
