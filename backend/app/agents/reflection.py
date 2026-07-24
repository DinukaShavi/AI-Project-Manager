from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class ReflectionResult:
    step_id: str
    confidence_score: float  # 0.0 to 1.0
    is_acceptable: bool
    critique: str
    suggested_action: str  # 'PROCEED', 'RETRY', 'REPLAN'

class ReflectionEngine:
    """Self-Reflection Engine evaluating step execution outputs, computing confidence scores, and generating critiques."""

    def __init__(self, confidence_threshold: float = 0.70):
        self.confidence_threshold = confidence_threshold

    def evaluate_step_output(
        self,
        step_id: str,
        step_name: str,
        execution_result: Dict[str, Any],
        expected_preconditions: Optional[Dict[str, Any]] = None
    ) -> ReflectionResult:
        """Evaluate raw output, calculate confidence score, and determine next step."""
        status = str(execution_result.get("status", "")).upper()
        output = execution_result.get("result") or execution_result.get("output") or {}

        # 1. Critical Failure Check
        if status in ("FAILURE", "EXECUTION_ERROR", "VALIDATION_FAILED", "PERMISSION_DENIED"):
            error_msg = execution_result.get("error") or execution_result.get("message") or "Unknown step execution error"
            return ReflectionResult(
                step_id=step_id,
                confidence_score=0.10,
                is_acceptable=False,
                critique=f"Step '{step_name}' failed with status '{status}': {error_msg}",
                suggested_action="REPLAN"
            )

        # 2. Waiting Approval Check
        if status == "WAITING_APPROVAL":
            return ReflectionResult(
                step_id=step_id,
                confidence_score=1.0,
                is_acceptable=True,
                critique=f"Step '{step_name}' suspended awaiting human approval.",
                suggested_action="PROCEED"
            )

        # 3. Output Payload Quality Check
        confidence = 0.95
        critique_notes = []

        if isinstance(output, str):
            if len(output.strip()) == 0:
                confidence -= 0.50
                critique_notes.append("Empty output returned.")
            elif "hallucinated" in output.lower() or "error" in output.lower():
                confidence -= 0.30
                critique_notes.append("Output contains failure/hallucination keywords.")
        elif isinstance(output, dict):
            if not output:
                confidence -= 0.40
                critique_notes.append("Empty JSON dict returned.")
            if "error" in output:
                confidence -= 0.35
                critique_notes.append(f"JSON output reports error: {output.get('error')}")

        is_acceptable = confidence >= self.confidence_threshold
        action = "PROCEED" if is_acceptable else ("RETRY" if confidence >= 0.40 else "REPLAN")
        critique_str = "; ".join(critique_notes) if critique_notes else "Output passed all quality heuristics."

        return ReflectionResult(
            step_id=step_id,
            confidence_score=max(0.0, min(1.0, confidence)),
            is_acceptable=is_acceptable,
            critique=f"Reflection on '{step_name}': {critique_str}",
            suggested_action=action
        )
