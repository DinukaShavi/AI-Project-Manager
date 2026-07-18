from typing import Any, Dict, List, Optional
from app.workflows.dag import WorkflowDAG, WorkflowNode

class PlanStep:
    def __init__(
        self,
        step_id: str,
        name: str,
        step_type: str, # 'agent' or 'tool'
        target: str,
        input_params: Dict[str, Any] = None,
        depends_on: List[str] = None
    ):
        self.step_id = step_id
        self.name = name
        self.step_type = step_type.lower()
        self.target = target
        self.input_params = input_params or {}
        self.depends_on = depends_on or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "step_type": self.step_type,
            "target": self.target,
            "input_params": self.input_params,
            "depends_on": self.depends_on
        }


class HTNPlanner:
    """Hierarchical Task Network (HTN) Planner decomposing complex goals into multi-agent DAGs."""

    def decompose_goal(self, goal: str, context: Optional[Dict[str, Any]] = None) -> List[PlanStep]:
        """Decompose high-level goal into hierarchical plan steps."""
        g_lower = goal.lower()
        steps: List[PlanStep] = []

        if "sprint" in g_lower or "release" in g_lower:
            steps.append(PlanStep(
                step_id="step_tpm_velocity",
                name="Sprint Velocity & Task Status Breakdown",
                step_type="agent",
                target="tpm",
                input_params={"task": f"Analyze sprint progress and issue statuses for goal: '{goal}'"}
            ))
            steps.append(PlanStep(
                step_id="step_code_diff",
                name="Pull Request Code Quality & Diff Audit",
                step_type="agent",
                target="code_analyst",
                input_params={"task": f"Inspect pull request diffs and test coverage for goal: '{goal}'"},
                depends_on=["step_tpm_velocity"]
            ))
            steps.append(PlanStep(
                step_id="step_risk_assessment",
                name="Delivery Bottleneck & Risk Assessment",
                step_type="agent",
                target="risk_manager",
                input_params={"task": f"Assess delivery bottlenecks and schedule risks for goal: '{goal}'"},
                depends_on=["step_code_diff"]
            ))
            steps.append(PlanStep(
                step_id="step_slack_notification",
                name="Broadcast Release Summary to Team",
                step_type="tool",
                target="slack_post_message",
                input_params={"channel": "#dev-announcements", "message": f"Sprint Release Audit complete for: {goal}"},
                depends_on=["step_risk_assessment"]
            ))

        elif "architecture" in g_lower or "design" in g_lower or "audit" in g_lower:
            steps.append(PlanStep(
                step_id="step_arch_review",
                name="Microservice Architecture & Schema Audit",
                step_type="agent",
                target="architect",
                input_params={"task": f"Review architectural compliance and API contracts for goal: '{goal}'"}
            ))
            steps.append(PlanStep(
                step_id="step_code_pattern",
                name="Implementation Code Pattern Analysis",
                step_type="agent",
                target="code_analyst",
                input_params={"task": f"Analyze code implementation against architecture design for goal: '{goal}'"},
                depends_on=["step_arch_review"]
            ))
            steps.append(PlanStep(
                step_id="step_tpm_assignments",
                name="Technical Task Backlog Assignment",
                step_type="agent",
                target="tpm",
                input_params={"task": f"Create backlog issues for architectural recommendations for goal: '{goal}'"},
                depends_on=["step_code_pattern"]
            ))

        else:
            # Default general HTN goal breakdown template
            steps.append(PlanStep(
                step_id="step_tpm_initial",
                name="Initial Goal Analysis & Scope Definition",
                step_type="agent",
                target="tpm",
                input_params={"task": f"Decompose requirements and define scope for goal: '{goal}'"}
            ))
            steps.append(PlanStep(
                step_id="step_code_review",
                name="Technical Strategy & Code Evaluation",
                step_type="agent",
                target="code_analyst",
                input_params={"task": f"Evaluate code readiness and technical feasibility for goal: '{goal}'"},
                depends_on=["step_tpm_initial"]
            ))

        return steps

    def build_dag_from_plan(self, steps: List[PlanStep]) -> WorkflowDAG:
        """Construct a validated WorkflowDAG from HTN plan steps."""
        dag = WorkflowDAG()
        for step in steps:
            dag.add_node(WorkflowNode(
                node_id=step.step_id,
                name=step.name,
                step_type=step.step_type,
                target=step.target,
                input_params=step.input_params,
                depends_on=step.depends_on
            ))
        dag.validate_dag()
        return dag
