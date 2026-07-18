import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization
from app.models.workflow import WorkflowDefinition, WorkflowExecution
from app.workflows.dag import WorkflowDAG, WorkflowNode
from app.services.workflow import WorkflowService
from app.db.session import SessionLocal

async def test_workflow_engine_flow():
    print("Initializing Workflow Engine validation tests...")

    # 1. Test DAG Topological Sorting & Cycle Detection
    print("\nTest 1: Testing WorkflowDAG topological levels & cycle detection...")
    dag = WorkflowDAG()
    n1 = WorkflowNode("step1", "Start", "agent", "tpm")
    n2 = WorkflowNode("step2", "Review Code", "agent", "code_analyst", depends_on=["step1"])
    n3 = WorkflowNode("step3", "Assess Risk", "agent", "risk_manager", depends_on=["step1"])
    n4 = WorkflowNode("step4", "Finalize", "agent", "architect", depends_on=["step2", "step3"])

    dag.add_node(n1)
    dag.add_node(n2)
    dag.add_node(n3)
    dag.add_node(n4)

    levels = dag.get_execution_levels()
    assert len(levels) == 3, f"Expected 3 parallel levels, got {len(levels)}"
    assert [n.node_id for n in levels[0]] == ["step1"]
    assert sorted([n.node_id for n in levels[1]]) == ["step2", "step3"]
    assert [n.node_id for n in levels[2]] == ["step4"]
    print("SUCCESS: Topological execution levels calculated correctly.")

    # Cycle detection
    n1.depends_on = ["step4"]
    try:
        dag.get_execution_levels()
        assert False, "Expected cycle detection exception"
    except ValueError as e:
        print(f"SUCCESS: Cycle detection correctly caught loop: {e}")
        n1.depends_on = []

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    created_def_ids = []
    created_exec_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization
            async with SessionLocal() as session:
                print("\nInserting test organization database entry...")
                org = Organization(name=f"Workflow Test Org {suffix}", domain=f"wf-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            # 2. Test Multi-Agent Sprint Review Workflow Execution
            print("\nTest 2: Testing Multi-Agent Sprint Review Workflow execution...")
            async with SessionLocal() as session:
                service = WorkflowService(session)
                sprint_dag = service.get_sprint_review_template_dag()
                execution = await service.execute_workflow(
                    dag=sprint_dag,
                    organization_id=test_org_id,
                    initial_context={"sprint": "Sprint 14", "team": "Core AI"}
                )
                created_exec_ids.append(execution.id)
                assert execution.status == "completed"
                node_outputs = execution.state_payload["node_outputs"]
                assert "tpm_analysis" in node_outputs
                assert "code_quality" in node_outputs
                assert "risk_evaluation" in node_outputs
                print("SUCCESS: Multi-agent Sprint Review DAG executed successfully across 3 steps.")

            # 3. Test HTTP API Endpoint: POST /api/v1/workflows/definitions
            print("\nTest 3: Requesting POST /api/v1/workflows/definitions...")
            res = await client.post(
                "/api/v1/workflows/definitions",
                json={
                    "organization_id": str(test_org_id),
                    "name": "Custom CI/CD Audit Workflow",
                    "description": "Custom automated code and architecture audit DAG",
                    "nodes": [
                        {"node_id": "review", "name": "Review PR", "step_type": "agent", "target": "code_analyst"},
                        {"node_id": "post_slack", "name": "Notify Slack", "step_type": "tool", "target": "slack_post_message", "input_params": {"channel": "#ci"}, "depends_on": ["review"]}
                    ]
                }
            )
            assert res.status_code == 201, f"Endpoint failed: {res.text}"
            def_json = res.json()
            def_id = uuid.UUID(def_json["definition_id"])
            created_def_ids.append(def_id)
            print(f"SUCCESS: Workflow Definition created via HTTP. ID: {def_json['definition_id']}")

            # 4. Test HTTP API Endpoint: GET /api/v1/workflows/definitions
            print("\nTest 4: Requesting GET /api/v1/workflows/definitions...")
            res = await client.get(f"/api/v1/workflows/definitions?organization_id={test_org_id}")
            assert res.status_code == 200
            defs_json = res.json()
            assert defs_json["definitions_count"] >= 1
            print(f"SUCCESS: GET /definitions returned {defs_json['definitions_count']} definitions.")

            # 5. Test HTTP API Endpoint: POST /api/v1/workflows/execute (Template)
            print("\nTest 5: Requesting POST /api/v1/workflows/execute (architecture_audit template)...")
            res = await client.post(
                "/api/v1/workflows/execute",
                json={
                    "organization_id": str(test_org_id),
                    "template": "architecture_audit",
                    "initial_context": {"component": "ContextEngine"}
                }
            )
            assert res.status_code == 200, f"Execution failed: {res.text}"
            exec_json = res.json()
            assert exec_json["status"] == "completed"
            exec_id = uuid.UUID(exec_json["execution_id"])
            created_exec_ids.append(exec_id)
            print(f"SUCCESS: Architecture Audit workflow executed via API. ID: {exec_json['execution_id']}")

            # 6. Test HTTP API Endpoint: GET /api/v1/workflows/executions/{id}
            print("\nTest 6: Requesting GET /api/v1/workflows/executions/{execution_id}...")
            res = await client.get(f"/api/v1/workflows/executions/{exec_id}")
            assert res.status_code == 200
            state_json = res.json()
            assert state_json["execution_id"] == str(exec_id)
            assert "arch_review" in state_json["state"]["node_outputs"]
            print("SUCCESS: Workflow execution state retrieved successfully via API.")

        finally:
            # Clean up database records
            print("\nCleaning up workflow engine test database entries...")
            async with SessionLocal() as session:
                for eid in created_exec_ids:
                    res = await session.execute(select(WorkflowExecution).where(WorkflowExecution.id == eid))
                    ex = res.scalar_one_or_none()
                    if ex:
                        await session.delete(ex)
                for did in created_def_ids:
                    res = await session.execute(select(WorkflowDefinition).where(WorkflowDefinition.id == did))
                    df = res.scalar_one_or_none()
                    if df:
                        await session.delete(df)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Workflow Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_workflow_engine_flow())
