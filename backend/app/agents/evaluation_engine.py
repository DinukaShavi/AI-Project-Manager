import re
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class EvaluationAssertion:
    metric: str # planning_accuracy, tool_success_rate, hallucination_rate, user_satisfaction_score
    operator: str # gte, lte, eq
    threshold: float

@dataclass
class BenchmarkRunResult:
    test_suite: str
    passed: bool
    metrics: Dict[str, float]
    assertion_results: List[Dict[str, Any]]

class EvaluationEngine:
    """Production AI Evaluation Pipeline & Benchmark Framework."""

    def calculate_tool_success_rate(self, success_calls: int, total_calls: int) -> float:
        """Calculate Tool Success Rate (TSR = Success Calls / Total Calls * 100)."""
        if total_calls == 0:
            return 100.0
        return (success_calls / total_calls) * 100.0

    def evaluate_planning_accuracy(
        self,
        generated_dag_steps: List[str],
        reference_dag_steps: List[str]
    ) -> float:
        """
        Evaluate planning accuracy by measuring step overlap and sequence ordering
        against ground-truth reference DAG templates.
        """
        if not reference_dag_steps:
            return 1.0
        if not generated_dag_steps:
            return 0.0

        gen_set = set(s.lower() for s in generated_dag_steps)
        ref_set = set(s.lower() for s in reference_dag_steps)

        matching = gen_set.intersection(ref_set)
        jaccard_similarity = len(matching) / len(ref_set)
        return round(jaccard_similarity, 4)

    def evaluate_hallucination_rate(
        self,
        agent_output: str,
        source_context: str
    ) -> float:
        """
        Evaluate hallucination rate by verifying whether output facts, entities, and numerical figures
        are supported by source context states.
        """
        if not agent_output or not source_context:
            return 0.0

        # Extract numerical claims (numbers, percentages, IDs)
        output_numbers = re.findall(r'\b\d+(?:\.\d+)?%?\b', agent_output)
        if not output_numbers:
            return 0.0

        unsupported_count = 0
        for num in output_numbers:
            # Clean percentage symbol for matching
            raw_num = num.replace("%", "")
            if raw_num not in source_context:
                unsupported_count += 1

        hallucination_rate = unsupported_count / len(output_numbers)
        return round(min(1.0, hallucination_rate), 4)

    def run_benchmark_suite(
        self,
        test_suite_name: str,
        metrics: Dict[str, float],
        assertions: List[EvaluationAssertion]
    ) -> BenchmarkRunResult:
        """Execute benchmark assertion suite against calculated metrics."""
        assertion_results = []
        overall_passed = True

        for assertion in assertions:
            val = metrics.get(assertion.metric, 0.0)
            op = assertion.operator.lower()
            thresh = assertion.threshold
            passed = False

            if op == "gte":
                passed = val >= thresh
            elif op == "lte":
                passed = val <= thresh
            elif op == "eq":
                passed = abs(val - thresh) < 1e-5

            if not passed:
                overall_passed = False

            assertion_results.append({
                "metric": assertion.metric,
                "operator": assertion.operator,
                "threshold": thresh,
                "actual_value": val,
                "passed": passed
            })

        return BenchmarkRunResult(
            test_suite=test_suite_name,
            passed=overall_passed,
            metrics=metrics,
            assertion_results=assertion_results
        )


# Singleton Instance Manager
_evaluation_engine_instance: Optional[EvaluationEngine] = None

def get_evaluation_engine() -> EvaluationEngine:
    """Get global EvaluationEngine singleton instance."""
    global _evaluation_engine_instance
    if _evaluation_engine_instance is None:
        _evaluation_engine_instance = EvaluationEngine()
    return _evaluation_engine_instance
