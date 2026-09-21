import json
import re
from typing import Any, Dict, List, Optional
from app.workflows.dag import WorkflowDAG, WorkflowNode
from app.planning.htn_domain import CompoundTask, PrimitiveTask, Method, Precondition
from app.agents.base import BaseAgent
from app.tools.registry import get_tool_registry

# The four real agent personas AgentService.get_agent actually knows how to instantiate
# (backend/app/services/agent.py:20-32) -- an LLM-generated plan step is only accepted if
# its "agent" target is one of these short aliases, so a hallucinated persona name can never
# reach execution.
AGENT_PERSONAS: Dict[str, str] = {
    "tpm": "Technical Project Manager -- sprint velocity, task status, and backlog analysis.",
    "code_analyst": "Code Analyst -- pull request diffs, commit quality, and test coverage review.",
    "risk_manager": "Risk Manager -- delivery risk, bottleneck, and Monte Carlo schedule forecasting.",
    "architect": "Architecture Reviewer -- system design, API contracts, and security pattern audit.",
}
MAX_LLM_PLAN_STEPS = 8


class _PlannerLLM(BaseAgent):
    """Minimal BaseAgent subclass whose only purpose is real `_llm_call`'s Claude/GPT-4o
    failover + circuit-breaker plumbing -- the exact same tested infrastructure every real
    agent persona already uses (Phase 69). `execute()` is never called; decomposition needs
    the LLM-calling mechanism, not a persona's conversational contract."""

    def __init__(self):
        super().__init__(
            agent_name="HTNPlanner",
            role="Goal Decomposition Planner",
            system_prompt="You decompose project management goals into a valid multi-step execution plan.",
        )

    async def execute(self, task_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError("_PlannerLLM is a carrier for _llm_call only.")

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
        self._planner_llm = _PlannerLLM()

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

    async def decompose_goal_async(self, goal: str, context: Optional[Dict[str, Any]] = None) -> List[PlanStep]:
        """Real LLM-driven decomposition (Step 7b). Asks Claude/GPT-4o -- via ModelRouter's
        DAG_GENERATION route (`app/core/model_router.py:27-34`), provisioned since the router
        was first built but never actually invoked anywhere until this method -- to produce a
        step DAG grounded in this specific goal and, when available, the real project subgraph,
        instead of matching the goal string against one of three fixed keyword templates.

        Never returns an invalid or unsafe plan: falls back to the deterministic keyword-
        template plan (`decompose_goal`, unchanged) whenever the LLM is unconfigured, the call
        fails, or its output doesn't parse into a plan whose every step targets a real agent
        persona or a real tool with valid parameters and forms a valid DAG. This is the same
        fallback tier `_llm_call` already applies per-provider (Claude -> GPT-4o -> synthetic
        text) -- an unparseable synthetic-text response falls through exactly like a network
        failure would, not a special case.

        Real tool-call safety is unaffected by this method either way: RBAC, approval gates,
        and tenant scoping in `ToolExecutor.execute_tool` apply identically to every tool step
        regardless of whether a human, a template, or this LLM path authored it."""
        try:
            steps = await self._decompose_with_llm(goal, context)
            if steps:
                return steps
        except Exception:
            pass
        return self.decompose_goal(goal, context)

    async def _decompose_with_llm(self, goal: str, context: Optional[Dict[str, Any]]) -> List[PlanStep]:
        tools = get_tool_registry().list_tools()
        tool_by_name = {t["name"]: get_tool_registry().get_tool(t["name"]) for t in tools}
        tool_lines = "\n".join(
            f'  - "{t["name"]}" (tool): {t["description"]} Required params: '
            f'{json.dumps(t["parameters_schema"].get("properties", {}))}'
            for t in tools
        )
        agent_lines = "\n".join(f'  - "{key}" (agent): {desc}' for key, desc in AGENT_PERSONAS.items())
        context_snippet = ""
        if context:
            context_snippet = f"\n\nRelevant project context:\n{json.dumps(context, default=str)[:1500]}"

        system_prompt = (
            "You are a technical project management planning engine. Decompose the goal below "
            "into a directed acyclic graph of 2 to 6 steps. Respond with ONLY a JSON array, no "
            "prose, no markdown code fences.\n\n"
            "Each step object must have exactly these fields:\n"
            '  "step_id": unique snake_case string\n'
            '  "name": short human-readable title\n'
            '  "step_type": either "agent" or "tool"\n'
            '  "target": for "agent" steps, one of the agent keys below; for "tool" steps, one '
            "of the tool names below\n"
            '  "input_params": object. For "agent" steps, include a "task" string describing '
            "exactly what to do. For \"tool\" steps, match the tool's required params exactly.\n"
            '  "depends_on": array of step_id strings that must complete first (empty array if none)\n\n'
            f"Available agents:\n{agent_lines}\n\n"
            f"Available tools:\n{tool_lines}"
        )
        user_prompt = f"Goal: {goal}{context_snippet}"

        raw_text = await self._planner_llm._llm_call(user_prompt, system_prompt, task_category="dag_generation")
        parsed = json.loads(self._extract_json_array(raw_text))
        if not isinstance(parsed, list) or not (1 <= len(parsed) <= MAX_LLM_PLAN_STEPS):
            raise ValueError(f"LLM plan was not a list of 1-{MAX_LLM_PLAN_STEPS} steps.")

        seen_ids = set()
        steps: List[PlanStep] = []
        for raw_step in parsed:
            step_id = raw_step["step_id"]
            if not isinstance(step_id, str) or not step_id or step_id in seen_ids:
                raise ValueError(f"Invalid or duplicate step_id: {step_id!r}")
            seen_ids.add(step_id)

            step_type = str(raw_step["step_type"]).lower()
            target = raw_step["target"]
            input_params = raw_step.get("input_params") or {}
            depends_on = raw_step.get("depends_on") or []
            if not isinstance(input_params, dict) or not isinstance(depends_on, list):
                raise ValueError(f"Malformed input_params/depends_on for step '{step_id}'.")

            if step_type == "agent":
                if target not in AGENT_PERSONAS:
                    raise ValueError(f"Unknown agent target '{target}' for step '{step_id}'.")
            elif step_type == "tool":
                if target not in tool_by_name:
                    raise ValueError(f"Unknown tool target '{target}' for step '{step_id}'.")
                is_valid, err = tool_by_name[target].validate_args(input_params)
                if not is_valid:
                    raise ValueError(f"Tool step '{step_id}' params invalid: {err}")
            else:
                raise ValueError(f"Unknown step_type '{step_type}' for step '{step_id}'.")

            steps.append(PlanStep(
                step_id=step_id,
                name=str(raw_step.get("name") or step_id),
                step_type=step_type,
                target=target,
                input_params=input_params,
                depends_on=[str(d) for d in depends_on],
            ))

        self.build_dag_from_plan(steps)  # raises on cycle / dangling dependency reference
        return steps

    @staticmethod
    def _extract_json_array(text: str) -> str:
        text = text.strip()
        fence_match = re.search(r"```(?:json)?\s*(\[.*\])\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1)
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON array found in LLM response.")
        return text[start:end + 1]

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
