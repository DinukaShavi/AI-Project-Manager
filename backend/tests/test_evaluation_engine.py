import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.agents.evaluation_engine import (
    get_evaluation_engine,
    EvaluationEngine,
    EvaluationAssertion
)

async def test_evaluation_engine_flow():
    print("Initializing AI Evaluation & Benchmark Framework validation tests...")
    engine = get_evaluation_engine()

    # 1. Test Tool Success Rate (TSR) Calculation
    print("\nTest 1: Testing Tool Success Rate (TSR) calculation...")
    tsr_100 = engine.calculate_tool_success_rate(10, 10)
    tsr_80 = engine.calculate_tool_success_rate(8, 10)
    assert tsr_100 == 100.0
    assert tsr_80 == 80.0
    print(f"SUCCESS: Tool Success Rate calculated correctly ({tsr_80}%).")

    # 2. Test Planning Accuracy Evaluation
    print("\nTest 2: Testing Planning Accuracy evaluation against reference DAG...")
    gen_dag = ["architecture_review", "database_migration", "api_deployment"]
    ref_dag = ["architecture_review", "database_migration", "api_deployment", "security_audit"]
    acc = engine.evaluate_planning_accuracy(gen_dag, ref_dag)
    assert acc == 0.75 # 3/4 step overlap
    print(f"SUCCESS: Planning accuracy calculated correctly ({acc * 100}%).")

    # 3. Test Hallucination Rate Detection
    print("\nTest 3: Testing Hallucination Rate contradiction detection...")
    context = "Project sprint backlog contains 5 open bugs and 2 pull requests."
    output_valid = "Sprint backlog has 5 open bugs and 2 pull requests."
    output_hallucinated = "Sprint backlog has 99 critical bugs and 88 pull requests."

    h_zero = engine.evaluate_hallucination_rate(output_valid, context)
    h_bad = engine.evaluate_hallucination_rate(output_hallucinated, context)
    assert h_zero == 0.0
    assert h_bad == 1.0 # 99 and 88 unsupported by source context
    print(f"SUCCESS: Hallucination rate evaluated correctly (valid: {h_zero}, hallucinated: {h_bad}).")

    # 4. Test Benchmark Suite Assertions Runner
    print("\nTest 4: Testing Benchmark Suite assertions runner...")
    assertions = [
        EvaluationAssertion(metric="planning_accuracy", operator="gte", threshold=0.70),
        EvaluationAssertion(metric="hallucination_rate", operator="lte", threshold=0.05),
        EvaluationAssertion(metric="tool_success_rate", operator="gte", threshold=90.0)
    ]
    metrics = {
        "planning_accuracy": 0.85,
        "hallucination_rate": 0.01,
        "tool_success_rate": 95.0
    }
    result = engine.run_benchmark_suite("sprint_planning_assessment", metrics, assertions)
    assert result.passed is True
    assert len(result.assertion_results) == 3
    print("SUCCESS: Benchmark suite assertions executed and passed.")

    # 5. Test REST API Endpoints
    print("\nTest 5: Testing Evaluation HTTP REST API endpoints...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST /api/v1/evaluations/evaluate-output
        res_eval = await client.post(
            "/api/v1/evaluations/evaluate-output",
            json={
                "agent_output": "Completed 5 tasks with 0 errors.",
                "source_context": "5 tasks queued for execution.",
                "success_calls": 5,
                "total_calls": 5
            }
        )
        assert res_eval.status_code == 200
        assert res_eval.json()["tool_success_rate"] == 100.0

        # POST /api/v1/evaluations/benchmark
        res_bench = await client.post(
            "/api/v1/evaluations/benchmark",
            json={
                "test_suite": "sprint_planning_assessment",
                "metrics": {"planning_accuracy": 0.95, "hallucination_rate": 0.01},
                "assertions": [
                    {"metric": "planning_accuracy", "operator": "gte", "threshold": 0.90},
                    {"metric": "hallucination_rate", "operator": "lte", "threshold": 0.02}
                ]
            }
        )
        assert res_bench.status_code == 200
        assert res_bench.json()["passed"] is True
        print("SUCCESS: Evaluation REST API endpoints verified.")

    print("\nAll AI Evaluation & Benchmark System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_evaluation_engine_flow())
