import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, Workspace
from app.models.project import Project, ProjectTask
from app.db.session import SessionLocal

async def test_full_api_suite_flow():
    print("Initializing Full Domain API Suite validation tests...")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    created_workspace_ids = []
    created_project_ids = []
    created_task_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization
            async with SessionLocal() as session:
                print("\nInserting test organization database entry...")
                org = Organization(name=f"Full API Test Org {suffix}", domain=f"api-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            # 1. Test Workspaces API: POST /api/v1/workspaces & GET /api/v1/workspaces
            print("\nTest 1: Testing Workspaces API endpoints...")
            res = await client.post(
                "/api/v1/workspaces",
                json={
                    "organization_id": str(test_org_id),
                    "name": "Backend Engineering Team"
                }
            )
            assert res.status_code == 201, f"Workspace creation failed: {res.text}"
            ws_json = res.json()
            ws_id = uuid.UUID(ws_json["workspace_id"])
            created_workspace_ids.append(ws_id)
            print(f"SUCCESS: Workspace created via API. ID: {ws_json['workspace_id']}")

            res = await client.get(f"/api/v1/workspaces?organization_id={test_org_id}")
            assert res.status_code == 200
            assert res.json()["workspaces_count"] >= 1
            print("SUCCESS: Workspaces listed via API.")

            # 2. Test Projects API: POST /api/v1/projects & GET /api/v1/projects/{id}
            print("\nTest 2: Testing Projects API endpoints...")
            res = await client.post(
                "/api/v1/projects",
                json={
                    "workspace_id": str(ws_id),
                    "name": "AI TPM Core System",
                    "description": "Enterprise Technical Project Manager System",
                    "jira_project_key": "TPM",
                    "github_repo_name": "acme/ai-tpm"
                }
            )
            assert res.status_code == 201, f"Project creation failed: {res.text}"
            proj_json = res.json()
            proj_id = uuid.UUID(proj_json["project_id"])
            created_project_ids.append(proj_id)
            print(f"SUCCESS: Project created via API. ID: {proj_json['project_id']}")

            res = await client.get(f"/api/v1/projects/{proj_id}")
            assert res.status_code == 200
            assert res.json()["jira_project_key"] == "TPM"
            print("SUCCESS: Project details retrieved via API.")

            # 3. Test Tasks API: POST /api/v1/tasks, GET /api/v1/tasks, PUT /api/v1/tasks/{id}
            print("\nTest 3: Testing Tasks API endpoints...")
            t1_res = await client.post(
                "/api/v1/tasks",
                json={
                    "project_id": str(proj_id),
                    "title": "Implement PostgreSQL pgvector fallback",
                    "status": "done",
                    "priority": "high",
                    "story_points": 5
                }
            )
            assert t1_res.status_code == 201
            created_task_ids.append(uuid.UUID(t1_res.json()["task_id"]))

            t2_res = await client.post(
                "/api/v1/tasks",
                json={
                    "project_id": str(proj_id),
                    "title": "Implement Sprint Velocity Analytics API",
                    "status": "in_progress",
                    "priority": "critical",
                    "story_points": 8
                }
            )
            assert t2_res.status_code == 201
            t2_id = uuid.UUID(t2_res.json()["task_id"])
            created_task_ids.append(t2_id)
            print("SUCCESS: 2 Tasks created via API.")

            res = await client.get(f"/api/v1/tasks?project_id={proj_id}")
            assert res.status_code == 200
            assert res.json()["tasks_count"] == 2
            print("SUCCESS: Project tasks listed via API.")

            # Update task status to done
            res = await client.put(f"/api/v1/tasks/{t2_id}", json={"status": "done"})
            assert res.status_code == 200
            assert res.json()["status"] == "done"
            print("SUCCESS: Task status updated via API.")

            # 4. Test Sprint Analytics API: GET /api/v1/analytics/sprint
            print("\nTest 4: Testing Sprint Analytics API endpoint...")
            res = await client.get(f"/api/v1/analytics/sprint?project_id={proj_id}")
            assert res.status_code == 200, f"Analytics failed: {res.text}"
            analytics_json = res.json()
            assert analytics_json["total_tasks"] == 2
            assert analytics_json["completed_tasks"] == 2
            assert analytics_json["completion_rate_percentage"] == 100.0
            print("SUCCESS: Sprint analytics metrics calculated correctly via API.")

        finally:
            # Clean up database records
            print("\nCleaning up full API suite test database entries...")
            async with SessionLocal() as session:
                for tid in created_task_ids:
                    res = await session.execute(select(ProjectTask).where(ProjectTask.id == tid))
                    t = res.scalar_one_or_none()
                    if t:
                        await session.delete(t)
                for pid in created_project_ids:
                    res = await session.execute(select(Project).where(Project.id == pid))
                    p = res.scalar_one_or_none()
                    if p:
                        await session.delete(p)
                for wid in created_workspace_ids:
                    res = await session.execute(select(Workspace).where(Workspace.id == wid))
                    w = res.scalar_one_or_none()
                    if w:
                        await session.delete(w)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Full Domain API Suite tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_full_api_suite_flow())
