import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User
from app.models.agent import AgentPlan
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_planning_tenant_isolation_flow():
    print("Initializing Planning Cross-Tenant Isolation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    plan_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Planning Tenant Org A {suffix}", domain=f"pio-a-{suffix}.com")
                org_b = Organization(name=f"Planning Tenant Org B {suffix}", domain=f"pio-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.commit()
            org_a_id, org_b_id = org_a.id, org_b.id
            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs and authenticated users created. Org A={org_a_id} Org B={org_b_id}")

            # Org A generates a real HTN plan via the real HTTP endpoint.
            secret_goal = f"CONFIDENTIAL-ORGA-{suffix}: Prepare acquisition due-diligence report."
            res = await client.post(
                "/api/v1/planning/plan",
                json={"goal": secret_goal},
                headers=headers_a,
            )
            assert res.status_code == 201, f"Plan generation failed: {res.text}"
            plan_a_id = res.json()["plan_id"]
            print(f"SUCCESS: Org A generated a real plan. Plan ID: {plan_a_id}")

            async with SessionLocal() as session:
                persisted = await session.get(AgentPlan, uuid.UUID(plan_a_id))
                assert persisted is not None
                assert persisted.organization_id == org_a_id

            # 1. Org A can retrieve its own plan.
            print("\nTest 1: Verifying Org A can retrieve its own plan...")
            res = await client.get(f"/api/v1/planning/plans/{plan_a_id}", headers=headers_a)
            assert res.status_code == 200, res.text
            assert res.json()["goal"] == secret_goal
            print("SUCCESS: Org A retrieved its own real plan.")

            # 2. Org B cannot retrieve Org A's plan by plan_id, and the response leaks
            # nothing (goal, plan_steps, plan_id).
            print("\nTest 2: Verifying Org B cannot retrieve Org A's plan...")
            res = await client.get(f"/api/v1/planning/plans/{plan_a_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            assert res.json()["detail"] == "Plan not found"
            raw_text = res.text
            assert secret_goal not in raw_text
            assert plan_a_id not in raw_text
            print("SUCCESS: Org B correctly rejected (404) with no leaked plan data.")

            # 3. A nonexistent plan_id returns the identical documented 404 (no
            # existence-leak between cross-tenant and nonexistent cases).
            print("\nTest 3: Verifying a nonexistent plan_id returns the same documented 404...")
            res = await client.get(f"/api/v1/planning/plans/{uuid.uuid4()}", headers=headers_a)
            assert res.status_code == 404
            assert res.json()["detail"] == "Plan not found"
            print("SUCCESS: Nonexistent plan_id correctly returns the documented 404.")

            # 4. THE CRITICAL CHECK: Org B cannot use POST /planning/execute with Org A's
            # plan_id to both trigger execution of Org A's plan AND read its goal/steps back
            # in the response. Before the fix, PlanningService.execute_plan looked up
            # plan_id with no organization_id filter at all.
            print("\nTest 4: Verifying Org B cannot execute Org A's plan via a supplied plan_id...")
            res = await client.post(
                "/api/v1/planning/execute",
                json={"plan_id": plan_a_id},
                headers=headers_b,
            )
            assert res.status_code == 400, f"Expected 400 (not found), got {res.status_code}: {res.text}"
            raw_text = res.text
            assert secret_goal not in raw_text, "Org A's confidential plan goal was leaked to Org B"
            assert "execution_id" not in raw_text
            print("SUCCESS: Org B correctly rejected when attempting to execute Org A's plan.")

            # 5. Org A's plan must remain completely unexecuted/untouched by Org B's
            # rejected attempt (still "generated", not "executing"/"executed"/"failed").
            print("\nTest 5: Verifying Org A's plan was not mutated by Org B's rejected attempt...")
            async with SessionLocal() as session:
                unchanged = await session.get(AgentPlan, uuid.UUID(plan_a_id))
                assert unchanged.status == "generated", f"Org B's rejected execute attempt must not mutate Org A's plan, got status={unchanged.status}"
            print("SUCCESS: Org A's plan status left unmodified.")

            # 6. Org A can still legitimately execute its own plan by plan_id (regression
            # guard -- the fix must not break legitimate same-tenant execution).
            print("\nTest 6: Verifying Org A can still execute its own plan...")
            res = await client.post(
                "/api/v1/planning/execute",
                json={"plan_id": plan_a_id},
                headers=headers_a,
            )
            assert res.status_code == 200, res.text
            exec_json = res.json()
            assert exec_json["plan_status"] == "executed"
            assert exec_json["goal"] == secret_goal
            print("SUCCESS: Org A's own plan_id-based execution still works correctly.")

            # 7. Org A retains full read access to its own plan after everything above.
            print("\nTest 7: Verifying Org A retains full working access after the fix...")
            res = await client.get(f"/api/v1/planning/plans/{plan_a_id}", headers=headers_a)
            assert res.status_code == 200
            print("SUCCESS: Org A retains full working access to its own plan.")

        finally:
            print("\nCleaning up planning tenant isolation test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    plan_res = await session.execute(select(AgentPlan).where(AgentPlan.organization_id == oid))
                    for p in plan_res.scalars().all():
                        await session.delete(p)
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

    print("\nAll Planning Cross-Tenant Isolation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_planning_tenant_isolation_flow())
