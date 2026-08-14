import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User, Workspace
from app.models.project import Project
from app.models.agent import AgentExecution
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_agent_execution_project_ownership_flow():
    print("Initializing Agent/Workflow Execution Project Ownership validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    shared_project_id = str(uuid.uuid4())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"ProjOwn Org A {suffix}", domain=f"projown-a-{suffix}.com")
                org_b = Organization(name=f"ProjOwn Org B {suffix}", domain=f"projown-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.commit()
                org_a_id, org_b_id = org_a.id, org_b.id

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs created. Org A={org_a_id} Org B={org_b_id}")

            # 1. Org A executes an agent with a project_id that doesn't exist yet -- the
            # existing "auto-create a demo project" convenience must still work, creating
            # the project under Org A's own organization (regression guard).
            print("\nTest 1: Verifying Org A's agent execution auto-creates the demo project under its own org...")
            res = await client.post(
                "/api/v1/agents/execute",
                json={"agent_type": "tpm", "task": "Org A confidential sprint analysis", "project_id": shared_project_id},
                headers=headers_a,
            )
            assert res.status_code == 200, f"Org A's execution failed: {res.text}"

            async with SessionLocal() as session:
                proj = await session.get(Project, uuid.UUID(shared_project_id))
                assert proj is not None
                assert proj.organization_id == org_a_id, "Auto-created demo project must belong to the calling organization"
            print("SUCCESS: Demo project auto-created and correctly owned by Org A.")

            # 2. THE CRITICAL CHECK: Org B executes an agent using the SAME project_id
            # (exactly what happens when two different real organizations both hit a
            # hardcoded DUMMY_PROJECT_ID from the frontend). Before the fix, this silently
            # succeeded and attached Org A's real project to Org B's execution.
            print("\nTest 2: Verifying Org B cannot attach Org A's project to its own execution...")
            res = await client.post(
                "/api/v1/agents/execute",
                json={"agent_type": "tpm", "task": "Org B task", "project_id": shared_project_id},
                headers=headers_b,
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            assert "not found in this organization" in res.text.lower()
            print("SUCCESS: Org B correctly rejected (400) when attempting to reuse Org A's project_id.")

            # 3. No AgentExecution row was created for Org B as a side effect of the
            # rejected attempt (fail closed, not fail open).
            print("\nTest 3: Verifying Org B's rejected attempt created no execution record...")
            async with SessionLocal() as session:
                res_db = await session.execute(select(AgentExecution).where(AgentExecution.organization_id == org_b_id))
                org_b_execs = res_db.scalars().all()
            assert len(org_b_execs) == 0, "A rejected cross-tenant project_id must not create any execution record"
            print("SUCCESS: No execution record was created for Org B's rejected attempt.")

            # 4. Org A can continue to reuse its own project_id normally (regression guard).
            print("\nTest 4: Verifying Org A retains full working access to its own project...")
            res = await client.post(
                "/api/v1/agents/execute",
                json={"agent_type": "code_analyst", "task": "Org A follow-up task", "project_id": shared_project_id},
                headers=headers_a,
            )
            assert res.status_code == 200, res.text
            print("SUCCESS: Org A's own repeated use of its project_id still works correctly.")

            # 5. The same root-cause protection covers the workflow-execution path, since
            # WorkflowExecutor's "agent" step type routes through the same execute_agent()
            # method -- Org B cannot attach Org A's project via a workflow execution either.
            print("\nTest 5: Verifying Org B cannot attach Org A's project via POST /workflows/execute...")
            res = await client.post(
                "/api/v1/workflows/execute",
                json={"template": "architecture_audit", "project_id": shared_project_id},
                headers=headers_b,
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            assert "not found in this organization" in res.text.lower()
            print("SUCCESS: Org B correctly rejected (400) attempting to reuse Org A's project_id via a workflow execution.")

        finally:
            print("\nCleaning up agent execution project ownership test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    exec_res = await session.execute(select(AgentExecution).where(AgentExecution.organization_id == oid))
                    for e in exec_res.scalars().all():
                        await session.delete(e)
                    await session.commit()

                proj = await session.get(Project, uuid.UUID(shared_project_id))
                if proj:
                    await session.delete(proj)
                    await session.commit()

                for oid in [o for o in [org_a_id, org_b_id] if o]:
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

    print("\nAll Agent/Workflow Execution Project Ownership tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_agent_execution_project_ownership_flow())
