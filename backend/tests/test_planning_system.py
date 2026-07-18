import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization
from app.models.agent import AgentPlan
from app.planning.planner import HTNPlanner
from app.services.planning import PlanningService
from app.db.session import SessionLocal

async def test_planning_system_flow():
    print("Initializing AI Planning System validation tests...")

    # 1. Test HTN Planner Goal Decomposition
    print("\nTest 1: Testing HTNPlanner goal decomposition & DAG generation...")
    planner = HTNPlanner()
    steps_sprint = planner.decompose_goal("Execute Sprint 14 Release & Risk Assessment")
    assert len(steps_sprint) == 4
    assert steps_sprint[0].target == "tpm"
    assert steps_sprint[3].target == "slack_post_message"

    dag = planner.build_dag_from_plan(steps_sprint)
    levels = dag.get_execution_levels()
    assert len(levels) == 4
    print("SUCCESS: Goal decomposed into 4-step DAG levels successfully.")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    created_plan_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization
            async with SessionLocal() as session:
                print("\nInserting test organization database entry...")
                org = Organization(name=f"Planning Test Org {suffix}", domain=f"plan-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            # 2. Test PlanningService Direct Generation & Execution
            print("\nTest 2: Testing PlanningService direct plan generation & execution...")
            async with SessionLocal() as session:
                service = PlanningService(session)
                plan = await service.generate_plan(
                    goal="Architecture Design Audit & API Review",
                    organization_id=test_org_id
                )
                created_plan_ids.append(plan.id)
                assert plan.status == "generated"
                assert len(plan.plan_steps) == 3
                print(f"SUCCESS: Plan stored in DB. ID: {plan.id}")

                executed_plan, execution = await service.execute_plan(plan_id=plan.id)
                assert executed_plan.status == "executed"
                assert execution.status == "completed"
                print("SUCCESS: Plan executed and state logged in DB.")

            # 3. Test HTTP API Endpoint: POST /api/v1/planning/plan
            print("\nTest 3: Requesting POST /api/v1/planning/plan...")
            res = await client.post(
                "/api/v1/planning/plan",
                json={
                    "organization_id": str(test_org_id),
                    "goal": "Prepare Sprint 15 Release Strategy"
                }
            )
            assert res.status_code == 201, f"Plan creation failed: {res.text}"
            p_json = res.json()
            pid = uuid.UUID(p_json["plan_id"])
            created_plan_ids.append(pid)
            assert p_json["steps_count"] == 4
            print(f"SUCCESS: Plan generated via HTTP API. ID: {p_json['plan_id']}")

            # 4. Test HTTP API Endpoint: GET /api/v1/planning/plans/{plan_id}
            print("\nTest 4: Requesting GET /api/v1/planning/plans/{plan_id}...")
            res = await client.get(f"/api/v1/planning/plans/{pid}")
            assert res.status_code == 200, f"Plan retrieval failed: {res.text}"
            rec_json = res.json()
            assert rec_json["goal"] == "Prepare Sprint 15 Release Strategy"
            print("SUCCESS: Plan retrieved via HTTP API.")

            # 5. Test HTTP API Endpoint: POST /api/v1/planning/execute
            print("\nTest 5: Requesting POST /api/v1/planning/execute...")
            res = await client.post(
                "/api/v1/planning/execute",
                json={
                    "organization_id": str(test_org_id),
                    "goal": "Execute Architecture Design Audit"
                }
            )
            assert res.status_code == 200, f"Plan execution failed: {res.text}"
            exec_json = res.json()
            assert exec_json["plan_status"] == "executed"
            assert exec_json["execution_status"] == "completed"
            created_plan_ids.append(uuid.UUID(exec_json["plan_id"]))
            print(f"SUCCESS: Plan decomposed & executed end-to-end via HTTP API. Execution ID: {exec_json['execution_id']}")

        finally:
            # Clean up database records
            print("\nCleaning up planning system test database entries...")
            async with SessionLocal() as session:
                for pid in created_plan_ids:
                    res = await session.execute(select(AgentPlan).where(AgentPlan.id == pid))
                    p = res.scalar_one_or_none()
                    if p:
                        await session.delete(p)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll AI Planning System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_planning_system_flow())
