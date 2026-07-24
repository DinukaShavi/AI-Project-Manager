import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base
from app.main import app
from app.agents.state_machine import AgentStateMachine, AgentState
from app.models.tenant import Organization
from app.models.agent import AgentExecution
from app.services.agent import AgentService
from app.db.session import SessionLocal

async def test_agent_state_machine_flow():
    print("Initializing Agent State Machine validation tests...")

    # 1. Test Valid & Invalid State Transitions
    print("\nTest 1: Testing valid vs invalid state machine transitions...")
    exec_id = uuid.uuid4()
    sm = AgentStateMachine(execution_id=exec_id, agent_name="tpm", initial_status=AgentState.CREATED)

    assert sm.can_transition(AgentState.QUEUED) is True
    assert sm.can_transition(AgentState.COMPLETED) is False # Cannot jump directly from CREATED to COMPLETED

    # Perform valid transition
    record = await sm.transition_to(AgentState.QUEUED, reason="Enqueued task")
    assert record["to_state"] == "QUEUED"
    assert sm.current_state == AgentState.QUEUED

    # Transition QUEUED -> PLANNING -> EXECUTING
    await sm.transition_to(AgentState.PLANNING)
    await sm.transition_to(AgentState.EXECUTING)
    assert sm.current_state == AgentState.EXECUTING
    print("SUCCESS: State transition rules verified.")

    # 2. Test Max Retries Exceeded
    print("\nTest 2: Testing max retries limit enforcement...")
    sm_retry = AgentStateMachine(execution_id=uuid.uuid4(), agent_name="code_analyst", initial_status=AgentState.REFLECTION, max_retries=2)
    
    await sm_retry.transition_to(AgentState.RETRYING) # retry_count = 1
    assert sm_retry.current_state == AgentState.RETRYING
    
    await sm_retry.transition_to(AgentState.EXECUTING)
    await sm_retry.transition_to(AgentState.REFLECTION)
    await sm_retry.transition_to(AgentState.RETRYING) # retry_count = 2
    assert sm_retry.current_state == AgentState.RETRYING

    await sm_retry.transition_to(AgentState.EXECUTING)
    await sm_retry.transition_to(AgentState.REFLECTION)
    await sm_retry.transition_to(AgentState.RETRYING) # retry_count = 3 > max_retries 2 -> FAILED
    assert sm_retry.current_state == AgentState.FAILED
    print("SUCCESS: Max retries threshold correctly forced FAILED state.")

    # 3. Test Worker Stale Heartbeat Detection
    print("\nTest 3: Testing worker stale heartbeat detection...")
    sm_heartbeat = AgentStateMachine(execution_id=uuid.uuid4(), agent_name="architect", heartbeat_timeout_seconds=2)
    assert sm_heartbeat.is_stale() is False
    
    # Simulate past heartbeat
    sm_heartbeat.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=5)
    assert sm_heartbeat.is_stale() is True
    print("SUCCESS: Worker crash/stale detection verified.")

    # 4. Test AgentService State Machine Lifecycle & DB Sync
    print("\nTest 4: Testing AgentService automatic state machine lifecycle & DB sync...")
    test_org_id = None
    async with SessionLocal() as session:
        service = AgentService(session)
        org = Organization(name=f"State Test Org {uuid.uuid4().hex[:6]}", domain=f"state-{uuid.uuid4().hex[:6]}.com")
        session.add(org)
        await session.flush()
        test_org_id = org.id
        await session.commit()

        execution = await service.execute_agent(
            agent_type="tpm",
            task_input="Review sprint backlog priorities",
            organization_id=test_org_id
        )
        assert execution.status.upper() == "COMPLETED"
        assert execution.execution_time_ms >= 0
        print(f"SUCCESS: Agent execution completed via State Machine. ID: {execution.id}")

    # 5. Test State Transition REST API Endpoint
    print("\nTest 5: Testing POST /api/v1/agents/executions/{execution_id}/transition API...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create execution entry
            async with SessionLocal() as session:
                exec_rec = AgentExecution(
                    organization_id=test_org_id,
                    agent_name="risk_manager",
                    status="EXECUTING",
                    input_payload={"task": "Assess risk"}
                )
                session.add(exec_rec)
                await session.commit()
                target_exec_id = exec_rec.id

            # Transition via API: EXECUTING -> WAITING_APPROVAL
            res = await client.post(
                f"/api/v1/agents/executions/{target_exec_id}/transition",
                json={
                    "target_state": "WAITING_APPROVAL",
                    "reason": "Requires manager approval for budget modification"
                }
            )
            assert res.status_code == 200, f"Transition failed: {res.text}"
            data = res.json()
            assert data["to_state"] == "WAITING_APPROVAL"
            print("SUCCESS: State machine transition executed via HTTP REST API.")

        finally:
            print("\nCleaning up State Machine test database records...")
            async with SessionLocal() as session:
                if test_org_id:
                    res_ex = await session.execute(select(AgentExecution).where(AgentExecution.organization_id == test_org_id))
                    for ex in res_ex.scalars().all():
                        await session.delete(ex)
                    res_org = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res_org.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                    await session.commit()
            print("Cleanup completed.")

    print("\nAll Agent State Machine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_agent_state_machine_flow())
