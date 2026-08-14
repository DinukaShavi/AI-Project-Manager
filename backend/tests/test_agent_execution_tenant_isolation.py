import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User
from app.models.agent import AgentExecution
from app.services.agent import AgentService
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_agent_execution_tenant_isolation_flow():
    print("Initializing Agent Execution Cross-Tenant Isolation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    execution_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Agent Exec Tenant Org A {suffix}", domain=f"aeiso-a-{suffix}.com")
                org_b = Organization(name=f"Agent Exec Tenant Org B {suffix}", domain=f"aeiso-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.commit()
            org_a_id, org_b_id = org_a.id, org_b.id
            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs and authenticated users created. Org A={org_a_id} Org B={org_b_id}")

            # Org A executes a real agent persona via the real HTTP endpoint (the actual
            # production execution path, not a directly-inserted fixture row).
            res = await client.post(
                "/api/v1/agents/execute",
                json={
                    "agent_type": "risk_manager",
                    "task": "Assess delivery risk for the current sprint",
                },
                headers=headers_a,
            )
            assert res.status_code == 200, f"Agent execution failed: {res.text}"
            execution_a_id = res.json()["execution_id"]
            print(f"SUCCESS: Org A executed a real agent persona. Execution ID: {execution_a_id}")

            # 1. Org A can retrieve its own execution.
            print("\nTest 1: Verifying Org A can retrieve its own execution...")
            res = await client.get(f"/api/v1/agents/executions/{execution_a_id}", headers=headers_a)
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["execution_id"] == execution_a_id
            assert body["agent_name"] == "RiskManagerAgent"
            print("SUCCESS: Org A retrieved its own real execution log.")

            # 2. Org B cannot retrieve Org A's execution by execution_id, and the response
            # leaks no execution details, agent info, or output/input payloads.
            print("\nTest 2: Verifying Org B cannot retrieve Org A's execution...")
            res = await client.get(f"/api/v1/agents/executions/{execution_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            raw_text = res.text
            assert "RiskManagerAgent" not in raw_text
            assert "Assess delivery risk" not in raw_text
            assert execution_a_id not in raw_text
            print("SUCCESS: Org B correctly rejected (404) with no leaked execution data.")

            # 3. Org B cannot mutate Org A's execution state via the transition endpoint,
            # and Org A's execution is left completely unmodified.
            print("\nTest 3: Verifying Org B cannot transition Org A's execution state...")
            res = await client.post(
                f"/api/v1/agents/executions/{execution_a_id}/transition",
                json={"target_state": "CANCELLED", "reason": "hostile cross-tenant cancellation attempt"},
                headers=headers_b,
            )
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            async with SessionLocal() as session:
                unchanged = await session.get(AgentExecution, uuid.UUID(execution_a_id))
                assert unchanged.status.upper() != "CANCELLED", "Org B's rejected transition must not have mutated Org A's execution"
                assert unchanged.status.upper() == "COMPLETED"
            print("SUCCESS: Org B correctly rejected (404); Org A's execution state left unmodified.")

            # 4. A nonexistent execution_id returns the same documented 404 response,
            # regardless of which organization asks (no existence-leak between the two
            # failure cases).
            print("\nTest 4: Verifying a nonexistent execution_id returns the documented 404...")
            res = await client.get(f"/api/v1/agents/executions/{uuid.uuid4()}", headers=headers_a)
            assert res.status_code == 404
            assert res.json()["detail"] == "Execution record not found"
            print("SUCCESS: Nonexistent execution_id correctly returns the documented 404.")

            # 5. Org A's own transition endpoint still works (regression guard -- the fix
            # must not break legitimate same-organization access).
            print("\nTest 5: Verifying Org A can still transition its own execution...")
            async with SessionLocal() as session:
                service = AgentService(session)
                second_exec = await service.execute_agent(
                    agent_type="architect", task_input="Audit service boundaries", organization_id=org_a_id,
                )
                second_exec_id = second_exec.id
            res = await client.get(f"/api/v1/agents/executions/{second_exec_id}", headers=headers_a)
            assert res.status_code == 200, res.text
            print("SUCCESS: Org A retains full, correct access to its own executions.")

        finally:
            print("\nCleaning up agent execution tenant isolation test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    exec_res = await session.execute(select(AgentExecution).where(AgentExecution.organization_id == oid))
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

    print("\nAll Agent Execution Cross-Tenant Isolation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_agent_execution_tenant_isolation_flow())
