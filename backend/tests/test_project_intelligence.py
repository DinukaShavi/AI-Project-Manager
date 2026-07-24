import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.context.graph import ProjectKnowledgeGraph, EntityNode
from app.planning.planner import HTNPlanner
from app.tools.executor import ToolExecutor
from app.agents.reflection import ReflectionEngine
from app.analytics.predictor import MonteCarloPredictor
from app.services.intelligence_engine import ProjectIntelligenceEngine

async def test_knowledge_graph_operations():
    print("Test 1: Testing Knowledge Graph entity & edge traversal...")
    graph = ProjectKnowledgeGraph()
    dev_node = EntityNode(urn="urn:user:dev1", type="developer", properties={"name": "Alice"})
    pr_node = EntityNode(urn="urn:github:pr:101", type="pull_request", properties={"title": "Fix Auth"})
    issue_node = EntityNode(urn="urn:jira:issue:TPM-50", type="jira_issue", properties={"status": "In Progress"})

    graph.add_entity(dev_node)
    graph.add_entity(pr_node)
    graph.add_entity(issue_node)

    graph.add_edge("urn:github:pr:101", "urn:jira:issue:TPM-50", "RESOLVES")
    graph.add_edge("urn:user:dev1", "urn:github:pr:101", "ASSIGNED_TO")

    subgraph = graph.get_subgraph_context("urn:jira:issue:TPM-50", max_depth=2)
    assert len(subgraph["nodes"]) >= 2
    assert len(subgraph["edges"]) >= 1
    print("SUCCESS: Knowledge Graph operations verified.")

async def test_htn_planner_replanning():
    print("Test 2: Testing HTN Planner decomposition and dynamic replanning loop...")
    planner = HTNPlanner()
    plan_steps = planner.decompose_goal("Audit sprint delivery health")
    assert len(plan_steps) >= 3

    revised_plan = planner.replan(
        original_plan=plan_steps,
        failed_step_id=plan_steps[0].step_id,
        failure_critique="Low confidence in sprint velocity calculation",
        current_state={}
    )
    assert len(revised_plan) > len(plan_steps)
    print("SUCCESS: HTN Planner replanning verified.")

async def test_tool_executor_approval_gates():
    print("Test 3: Testing Tool Executor capability matching and approval gates...")
    executor = ToolExecutor()

    # Normal read tool
    res1 = await executor.execute_tool("jira_get_issue", {"issue_key": "TPM-101"})
    assert res1["status"] in ("SUCCESS", "EXECUTION_ERROR")

    # High-risk side-effect tool without approval token
    res2 = await executor.execute_tool("merge_pull_request", {"pr_number": 42})
    assert res2["status"] == "WAITING_APPROVAL"
    print("SUCCESS: Tool Executor approval gates verified.")

async def test_reflection_engine_confidence():
    print("Test 4: Testing Self-Reflection Engine confidence evaluation...")
    reflection = ReflectionEngine(confidence_threshold=0.70)
    good_res = reflection.evaluate_step_output(
        step_id="s1",
        step_name="Step 1",
        execution_result={"status": "SUCCESS", "result": {"data": "valid analytical output"}}
    )
    assert good_res.is_acceptable is True
    assert good_res.confidence_score >= 0.70

    bad_res = reflection.evaluate_step_output(
        step_id="s2",
        step_name="Step 2",
        execution_result={"status": "EXECUTION_ERROR", "error": "Database timeout"}
    )
    assert bad_res.is_acceptable is False
    assert bad_res.suggested_action == "REPLAN"
    print("SUCCESS: Self-Reflection confidence evaluation verified.")

async def test_monte_carlo_simulation():
    print("Test 5: Testing Monte Carlo 1,000-run velocity simulation...")
    mc_res = MonteCarloPredictor.run_simulation(
        historical_velocities=[6.0, 7.0, 5.0, 8.0],
        remaining_points=20.0,
        num_simulations=100
    )
    assert mc_res["num_simulations"] == 100
    assert "p50_days" in mc_res
    assert "p95_days" in mc_res
    assert mc_res["p95_days"] >= mc_res["p50_days"]
    print("SUCCESS: Monte Carlo simulation verified.")

async def test_intelligence_engine_end_to_end():
    print("Test 6: Testing Project Intelligence Engine end-to-end processing...")
    engine = ProjectIntelligenceEngine()
    res = await engine.process_goal(
        goal="Audit release readiness and sprint risk",
        organization_id=str(uuid.uuid4()),
        user_role="Developer"
    )
    assert "run_id" in res
    assert "knowledge_graph" in res
    assert "plan_execution" in res
    assert "monte_carlo_predictive" in res
    assert "recommendations" in res
    print("SUCCESS: Project Intelligence Engine end-to-end verified.")

async def test_intelligence_http_endpoint():
    print("Test 7: Requesting POST /api/v1/planning/intelligence...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "organization_id": str(uuid.uuid4()),
            "goal": "Audit microservices architecture compliance",
            "user_role": "Developer"
        }
        res = await client.post("/api/v1/planning/intelligence", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "run_id" in data
        assert len(data["recommendations"]) > 0
    print("SUCCESS: HTTP intelligence endpoint verified.")

async def test_project_intelligence_flow():
    print("Initializing Project Intelligence Engine validation tests...")
    await test_knowledge_graph_operations()
    await test_htn_planner_replanning()
    await test_tool_executor_approval_gates()
    await test_reflection_engine_confidence()
    await test_monte_carlo_simulation()
    await test_intelligence_engine_end_to_end()
    await test_intelligence_http_endpoint()
    print("All Project Intelligence Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_project_intelligence_flow())
