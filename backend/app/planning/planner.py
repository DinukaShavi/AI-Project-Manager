from typing import Any, Dict, List, Optional
from app.workflows.dag import WorkflowDAG, WorkflowNode
from app.planning.htn_domain import CompoundTask, PrimitiveTask, Method, Precondition

class PlanStep:
    def __init__(
        self,
        step_id: str,
        name: str,
        step_type: str,  # 'agent' or 'tool'
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
    """Hierarchical Task Network (HTN) Planner decomposing complex goals into multi-agent DAGs with replanning capability."""

    def __init__(self):
        self.registered_methods: List[Method] = []
        self._register_default_domain_methods()

    def _register_default_domain_methods(self):
        """Register domain decomposition methods for HTN planning."""
        # Method for Sprint Delivery Audit
        self.registered_methods.append(
            Method(
                name="AuditSprintHealthMethod",
                target_compound_task="AuditSprintHealth",
                preconditions=[Precondition(name="AlwaysTrue", predicate=lambda s: True)],
                subtasks=[
                    PrimitiveTask(name="Analyze Sprint Velocity", operator_name="agent", tool_binding="tpm"),
                    PrimitiveTask(name="Audit PR Code Diffs", operator_name="agent", tool_binding="code_analyst"),
                    PrimitiveTask(name="Assess Delivery Risks", operator_name="agent", tool_binding="risk_manager"),
                    PrimitiveTask(name="Broadcast Slack Alert", operator_name="tool", tool_binding="slack_post_message")
                ]
            )
        )

        # Method for Architecture Review
        self.registered_methods.append(
            Method(
                name="AuditArchitectureMethod",
                target_compound_task="AuditArchitectureCompliance",
                preconditions=[Precondition(name="AlwaysTrue", predicate=lambda s: True)],
                subtasks=[
                    PrimitiveTask(name="Review System Design & Contracts", operator_name="agent", tool_binding="architect"),
                    PrimitiveTask(name="Inspect Code Pattern Quality", operator_name="agent", tool_binding="code_analyst"),
                    PrimitiveTask(name="Assign Backlog Remediation", operator_name="agent", tool_binding="tpm")
                ]
            )
        )

    def decompose_goal(self, goal: str, context: Optional[Dict[str, Any]] = None) -> List[PlanStep]:
        """Decompose high-level goal into hierarchical plan steps using HTN domain or fallback templates."""
        g_lower = goal.lower()
        context_state = context or {}
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

    def replan(
        self,
        original_plan: List[PlanStep],
        failed_step_id: str,
        failure_critique: str,
        current_state: Dict[str, Any]
    ) -> List[PlanStep]:
        """Dynamic mid-execution replanning loop when step execution fails or receives low confidence."""
        revised_steps: List[PlanStep] = []
        for step in original_plan:
            if step.step_id == failed_step_id:
                # Insert dynamic recovery step before retrying
                recovery_step = PlanStep(
                    step_id=f"{failed_step_id}_recovery",
                    name=f"Recovery & Strategy Adjustment for {step.name}",
                    step_type="agent",
                    target="risk_manager",
                    input_params={
                        "task": f"Re-evaluate strategy due to failure in '{step.name}'. Critique: {failure_critique}",
                        "failed_step": step.step_id
                    },
                    depends_on=step.depends_on
                )
                revised_steps.append(recovery_step)
                
                # Retry step with updated dependencies
                retried_step = PlanStep(
                    step_id=f"{failed_step_id}_retry",
                    name=f"{step.name} (Retried)",
                    step_type=step.step_type,
                    target=step.target,
                    input_params={**step.input_params, "critique_feedback": failure_critique},
                    depends_on=[recovery_step.step_id]
                )
                revised_steps.append(retried_step)
            else:
                revised_steps.append(step)

        return revised_steps

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
