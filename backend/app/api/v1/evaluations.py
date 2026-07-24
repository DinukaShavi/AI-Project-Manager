from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from app.agents.evaluation_engine import (
    get_evaluation_engine,
    EvaluationAssertion
)

router = APIRouter(prefix="/evaluations", tags=["AI Evaluations & Benchmarks"])

class AssertionDTO(BaseModel):
    metric: str
    operator: str # gte, lte, eq
    threshold: float

class BenchmarkRunRequest(BaseModel):
    test_suite: str
    metrics: Dict[str, float]
    assertions: List[AssertionDTO]

class EvaluateOutputRequest(BaseModel):
    agent_output: str
    source_context: str
    generated_dag_steps: Optional[List[str]] = None
    reference_dag_steps: Optional[List[str]] = None
    success_calls: int = 0
    total_calls: int = 0

@router.post("/evaluate-output")
async def evaluate_agent_output(payload: EvaluateOutputRequest):
    """Evaluate planning accuracy, TSR, and hallucination rate for an agent execution run."""
    engine = get_evaluation_engine()
    tsr = engine.calculate_tool_success_rate(payload.success_calls, payload.total_calls)
    hallucination_rate = engine.evaluate_hallucination_rate(payload.agent_output, payload.source_context)
    
    planning_acc = 1.0
    if payload.generated_dag_steps and payload.reference_dag_steps:
        planning_acc = engine.evaluate_planning_accuracy(payload.generated_dag_steps, payload.reference_dag_steps)

    return {
        "tool_success_rate": tsr,
        "hallucination_rate": hallucination_rate,
        "planning_accuracy": planning_acc
    }

@router.post("/benchmark")
async def run_benchmark_assertions(payload: BenchmarkRunRequest):
    """Execute benchmark assertions pipeline over agent run metrics."""
    engine = get_evaluation_engine()
    assertions = [
        EvaluationAssertion(metric=a.metric, operator=a.operator, threshold=a.threshold)
        for a in payload.assertions
    ]
    res = engine.run_benchmark_suite(
        test_suite_name=payload.test_suite,
        metrics=payload.metrics,
        assertions=assertions
    )
    return {
        "test_suite": res.test_suite,
        "passed": res.passed,
        "metrics": res.metrics,
        "assertion_results": res.assertion_results
    }
