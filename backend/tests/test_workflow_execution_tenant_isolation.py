import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User
from app.models.workflow import WorkflowExecution
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_workflow_execution_tenant_isolation_flow():
    print("Initializing Workflow Execution Cross-Tenant Isolation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    execution_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Workflow Exec Tenant Org A {suffix}", domain=f"weiso-a-{suffix}.com")
                org_b = Organization(name=f"Workflow Exec Tenant Org B {suffix}", domain=f"weiso-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.commit()
            org_a_id, org_b_id = org_a.id, org_b.id
            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs and authenticated users created. Org A={org_a_id} Org B={org_b_id}")

            # 1. Org A executes a real multi-agent workflow DAG via the real HTTP endpoint
            # (the actual production execution path, not a directly-inserted fixture row).
            res = await client.post(
                "/api/v1/workflows/execute",
                json={"template": "architecture_audit", "initial_context": {"component": "TenantIsolationTest"}},
                headers=headers_a,
            )
            assert res.status_code == 200, f"Workflow execution failed: {res.text}"
            execution_a_id = res.json()["execution_id"]
            print(f"SUCCESS: Org A executed a real workflow DAG. Execution ID: {execution_a_id}")

            # Verify the created row actually persisted organization_id explicitly (not
            # relying solely on an implicit session-context side-channel).
            async with SessionLocal() as session:
                persisted = await session.get(WorkflowExecution, uuid.UUID(execution_a_id))
                assert persisted is not None
                assert persisted.organization_id == org_a_id, "WorkflowExecution.organization_id must be set to the real owning organization"

            # 2. Org A can retrieve its own execution.
            print("\nTest 2: Verifying Org A can retrieve its own execution...")
            res = await client.get(f"/api/v1/workflows/executions/{execution_a_id}", headers=headers_a)
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["execution_id"] == execution_a_id
            assert "arch_review" in body["state"]["node_outputs"]
            print("SUCCESS: Org A retrieved its own real workflow execution.")

            # 3. Org B cannot retrieve Org A's execution by execution_id, and receives the
            # documented generic not-found response with no leaked details.
            print("\nTest 3: Verifying Org B cannot retrieve Org A's workflow execution...")
            res = await client.get(f"/api/v1/workflows/executions/{execution_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            assert res.json()["detail"] == "Workflow execution not found"
            raw_text = res.text
            assert "arch_review" not in raw_text
            assert "TenantIsolationTest" not in raw_text
            assert "node_outputs" not in raw_text
            assert "final_context" not in raw_text
            assert execution_a_id not in raw_text
            print("SUCCESS: Org B correctly rejected (404) with no leaked execution data.")

            # 4. A nonexistent execution_id returns the exact same documented not-found
            # response as the cross-tenant case -- no existence-leak between the two.
            print("\nTest 4: Verifying a nonexistent execution_id returns the same documented 404...")
            res = await client.get(f"/api/v1/workflows/executions/{uuid.uuid4()}", headers=headers_a)
            assert res.status_code == 404
            assert res.json()["detail"] == "Workflow execution not found"
            print("SUCCESS: Nonexistent execution_id correctly returns the documented 404.")

            # 5. Org A retains full, correct access to its own execution after the fix
            # (regression guard).
            print("\nTest 5: Verifying Org A's own access still works after the fix...")
            res = await client.get(f"/api/v1/workflows/executions/{execution_a_id}", headers=headers_a)
            assert res.status_code == 200
            print("SUCCESS: Org A retains full working access to its own workflow execution.")

        finally:
            print("\nCleaning up workflow execution tenant isolation test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    exec_res = await session.execute(select(WorkflowExecution).where(WorkflowExecution.organization_id == oid))
                    for e in exec_res.scalars().all():
                        await session.delete(e)
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

    print("\nAll Workflow Execution Cross-Tenant Isolation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_workflow_execution_tenant_isolation_flow())
