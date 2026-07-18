import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization
from app.models.agent import AgentExecution
from app.agents.tpm import TechnicalPMAgent
from app.agents.code_analyst import CodeAnalystAgent
from app.agents.risk_manager import RiskManagerAgent
from app.agents.architect import ArchitectureReviewerAgent
from app.services.agent import AgentService
from app.db.session import SessionLocal

async def test_agent_framework_flow():
    print("Initializing AI Agent Framework validation tests...")

    # 1. Test Agent Persona Instantiations
    print("\nTest 1: Testing specialized agent persona instantiations...")
    tpm = TechnicalPMAgent()
    ca = CodeAnalystAgent()
    rm = RiskManagerAgent()
    arch = ArchitectureReviewerAgent()

    assert tpm.role == "Technical Project Manager"
    assert ca.role == "Senior Code Analyst & Reviewer"
    assert rm.role == "Project Risk Manager"
    assert arch.role == "System Architect"
    print("SUCCESS: All 4 agent personas initialized correctly.")

    # 2. Test Direct Agent Task Executions
    print("\nTest 2: Testing direct agent task execution outputs...")
    res_tpm = await tpm.execute("Review sprint velocity for Team Alpha", {"sprint_id": "sprint-42"})
    assert res_tpm["agent"] == "TechnicalPMAgent"
    assert "analysis" in res_tpm

    res_ca = await ca.execute("Analyze pull request #101 diff for memory leaks", {"pr_id": 101})
    assert res_ca["agent"] == "CodeAnalystAgent"
    assert res_ca["code_quality_score"] > 0

    res_rm = await rm.execute("Assess scope creep risk for release 1.0", {"delay_days": 3})
    assert res_rm["agent"] == "RiskManagerAgent"

    res_arch = await arch.execute("Verify microservice event outbox architecture", {"pattern": "outbox"})
    assert res_arch["agent"] == "ArchitectureReviewerAgent"
    print("SUCCESS: Direct agent task execution completed across all 4 personas.")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    created_execution_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization
            async with SessionLocal() as session:
                print("\nInserting test organization database entry...")
                org = Organization(name=f"Agent Test Org {suffix}", domain=f"agent-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            # 3. Test AgentService Direct Execution & DB Persistence
            print("\nTest 3: Testing AgentService direct execution & database logging...")
            async with SessionLocal() as session:
                service = AgentService(session)
                execution = await service.execute_agent(
                    agent_type="tpm",
                    task_input="Generate sprint capacity recommendations",
                    organization_id=test_org_id,
                    context={"team_size": 5}
                )
                created_execution_ids.append(execution.id)
                assert execution.status == "completed"
                assert execution.agent_name == "TechnicalPMAgent"
                assert execution.execution_time_ms >= 0
                print(f"SUCCESS: Agent execution logged in DB. Execution ID: {execution.id}")

            # 4. Test HTTP API Endpoint: POST /api/v1/agents/execute
            print("\nTest 4: Requesting POST /api/v1/agents/execute...")
            res = await client.post(
                "/api/v1/agents/execute",
                json={
                    "agent_type": "architect",
                    "task": "Review PostgreSQL pgvector fallback strategy",
                    "organization_id": str(test_org_id),
                    "context": {"database": "postgresql"}
                }
            )
            assert res.status_code == 200, f"Endpoint failed: {res.text}"
            res_json = res.json()
            assert res_json["status"] == "completed"
            assert res_json["agent_name"] == "ArchitectureReviewerAgent"
            exec_id = uuid.UUID(res_json["execution_id"])
            created_execution_ids.append(exec_id)
            print(f"SUCCESS: HTTP agent execution accepted. Execution ID: {res_json['execution_id']}")

            # 5. Test HTTP API Endpoint: GET /api/v1/agents/executions/{id}
            print("\nTest 5: Requesting GET /api/v1/agents/executions/{execution_id}...")
            res = await client.get(f"/api/v1/agents/executions/{exec_id}")
            assert res.status_code == 200, f"Get execution failed: {res.text}"
            log_json = res.json()
            assert log_json["execution_id"] == str(exec_id)
            assert log_json["agent_name"] == "ArchitectureReviewerAgent"
            print("SUCCESS: Execution log fetched successfully via API.")

        finally:
            # Clean up database records
            print("\nCleaning up agent framework test database entries...")
            async with SessionLocal() as session:
                for eid in created_execution_ids:
                    res = await session.execute(select(AgentExecution).where(AgentExecution.id == eid))
                    ex = res.scalar_one_or_none()
                    if ex:
                        await session.delete(ex)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll AI Agent Framework tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_agent_framework_flow())
