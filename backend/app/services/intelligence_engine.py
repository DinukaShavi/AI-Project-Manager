from typing import Dict, Any, List, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.graph import ProjectKnowledgeGraph, EntityNode
from app.context.embeddings import HybridContextRetriever
from app.planning.planner import HTNPlanner, PlanStep
from app.tools.executor import ToolExecutor
from app.agents.reflection import ReflectionEngine, ReflectionResult
from app.analytics.predictor import MonteCarloPredictor, PredictiveAnalyticsEngine
from app.analytics.recommendation import RecommendationEngine


class ProjectIntelligenceEngine:
    """Enterprise-grade AI Project Intelligence Engine unifying Knowledge Graph reasoning, HTN planning, tool approvals, self-reflection, and Monte Carlo predictions."""

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.graph = ProjectKnowledgeGraph()
        self.planner = HTNPlanner()
        self.executor = ToolExecutor()
        self.reflection = ReflectionEngine()
        self.mc_predictor = MonteCarloPredictor()
        self.recommendation_engine = RecommendationEngine()
        self.hybrid_retriever = HybridContextRetriever()

    async def process_goal(
        self,
        goal: str,
        organization_id: str,
        project_id: Optional[str] = None,
        user_role: str = "Developer",
        approval_token: Optional[str] = None,
        historical_velocities: Optional[List[float]] = None,
        remaining_points: float = 25.0
    ) -> Dict[str, Any]:
        """Execute unified 5-stage Project Intelligence Pipeline."""
        run_id = str(uuid.uuid4())

        # Stage 1: Load/Build Knowledge Graph & Subgraph Context
        if self.db and project_id:
            await self.graph.load_from_db(self.db, organization_id, project_id)

        subgraph_context = self.graph.get_subgraph_context(entity_urn=project_id or "default_entity")

        # Stage 2: HTN Goal Decomposition into Execution DAG
        steps: List[PlanStep] = self.planner.decompose_goal(goal, context={"subgraph": subgraph_context})

        # Stage 3: Step Execution, Approval Gate Evaluation & Self-Reflection Loop
        executed_steps: List[Dict[str, Any]] = []
        reflection_logs: List[Dict[str, Any]] = []
        replan_triggered = False

        for step in steps:
            # Execute step via ToolExecutor or Agent Persona Simulation
            if step.step_type == "tool":
                tool_res = await self.executor.execute_tool(
                    tool_name=step.target,
                    parameters=step.input_params,
                    user_role=user_role,
                    approval_token=approval_token,
                    agent_execution_id=run_id
                )
            else:
                tool_res = {
                    "status": "SUCCESS",
                    "result": {
                        "agent": step.target,
                        "analysis": f"Synthetic reasoning analysis completed for {step.name}.",
                        "task_inputs": step.input_params
                    }
                }

            # Run Stage 4: Reflection Engine Critique
            reflection_res: ReflectionResult = self.reflection.evaluate_step_output(
                step_id=step.step_id,
                step_name=step.name,
                execution_result=tool_res
            )

            reflection_logs.append({
                "step_id": step.step_id,
                "confidence_score": reflection_res.confidence_score,
                "is_acceptable": reflection_res.is_acceptable,
                "critique": reflection_res.critique,
                "action": reflection_res.suggested_action
            })

            # Check if dynamic HTN replanning is required
            if reflection_res.suggested_action == "REPLAN" and not replan_triggered:
                replan_triggered = True
                revised_steps = self.planner.replan(
                    original_plan=steps,
                    failed_step_id=step.step_id,
                    failure_critique=reflection_res.critique,
                    current_state={"graph": subgraph_context}
                )
                tool_res["replan_note"] = f"HTN Replanner triggered. Revised plan step count: {len(revised_steps)}"

            executed_steps.append({
                "step_id": step.step_id,
                "name": step.name,
                "type": step.step_type,
                "target": step.target,
                "result": tool_res
            })

        # Stage 5: Monte Carlo Simulation & Risk Recommendations
        mc_results = self.mc_predictor.run_simulation(
            historical_velocities=historical_velocities or [6.0, 7.0, 5.5, 8.0],
            remaining_points=remaining_points
        )

        recommendations = self.recommendation_engine.generate_recommendations(
            graph_state=self.graph,
            monte_carlo_results=mc_results
        )

        return {
            "run_id": run_id,
            "goal": goal,
            "organization_id": organization_id,
            "project_id": project_id,
            "knowledge_graph": {
                "nodes_count": len(self.graph.nodes),
                "edges_count": len(self.graph.edges),
                "subgraph_summary": subgraph_context
            },
            "plan_execution": {
                "total_steps": len(steps),
                "replan_triggered": replan_triggered,
                "executed_steps": executed_steps
            },
            "reflection_audit": reflection_logs,
            "monte_carlo_predictive": mc_results,
            "recommendations": recommendations
        }
