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
from app.services.recommendation import RecommendationService


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
        remaining_points: Optional[float] = None
    ) -> Dict[str, Any]:
        """Execute unified 5-stage Project Intelligence Pipeline."""
        run_id = str(uuid.uuid4())

        # Stage 1: Load/Build Knowledge Graph & Subgraph Context
        if self.db and project_id:
            await self.graph.load_from_db(self.db, organization_id, project_id)

        subgraph_context = self.graph.get_subgraph_context(entity_urn=project_id or "default_entity")

        # Stage 2: HTN Goal Decomposition into Execution DAG -- real LLM-driven decomposition
        # (Step 7b) when available, gracefully falling back to the deterministic keyword-
        # template plan otherwise; see HTNPlanner.decompose_goal_async.
        steps: List[PlanStep] = await self.planner.decompose_goal_async(goal, context={"subgraph": subgraph_context})

        # Stage 3: Step Execution, Approval Gate Evaluation & Self-Reflection Loop
        executed_steps: List[Dict[str, Any]] = []
        reflection_logs: List[Dict[str, Any]] = []
        replan_triggered = False

        for step in steps:
            # Execute step via ToolExecutor or a real Agent Persona execution
            if step.step_type == "tool":
                # Pass the real session/tenant context through so high-risk steps resolve
                # against real ToolApproval grants (Phase 86) instead of tripping the
                # executor's fail-closed branch, and so every outcome is audit-logged.
                tool_res = await self.executor.execute_tool(
                    tool_name=step.target,
                    parameters=step.input_params,
                    user_role=user_role,
                    approval_token=approval_token,
                    agent_execution_id=run_id,
                    db=self.db,
                    organization_id=uuid.UUID(str(organization_id)) if organization_id else None,
                )
            elif self.db is not None:
                tool_res = await self._execute_real_agent_step(
                    step=step,
                    organization_id=organization_id,
                    project_id=project_id,
                    subgraph_context=subgraph_context,
                )
            else:
                # No DB session available (e.g. ProjectIntelligenceEngine() used directly in
                # a unit test exercising just the planner/reflection/replan mechanics) --
                # real agent execution needs a session to persist AgentExecution rows and load
                # real context, so this mirrors the same self.db guard Stage 1 already uses
                # for graph loading, rather than a new shortcut.
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

        # Stage 5: Monte Carlo Simulation & Risk Recommendations, grounded in this project's
        # real velocity/remaining-work data when the caller didn't explicitly override it
        # (Phase 80) rather than always falling back to hardcoded example numbers.
        resolved_velocities, resolved_points, forecast_data_source = await self._resolve_forecast_inputs(
            organization_id, project_id, historical_velocities, remaining_points
        )
        mc_results = self.mc_predictor.run_simulation(
            historical_velocities=resolved_velocities,
            remaining_points=resolved_points
        )

        recommendations = self.recommendation_engine.generate_recommendations(
            graph_state=self.graph,
            monte_carlo_results=mc_results
        )

        # Persist to the Recommendation Log (detailed_component_architecture.md section 7)
        # so GET /api/v1/recommendations (api_contract.md 12.A) can serve them. Only
        # possible when both a DB session and a real project_id are available -- project_id
        # is a required (non-nullable) FK on the recommendations table, and a goal processed
        # without a project context has nothing to attach persisted recommendations to.
        if self.db and project_id:
            await RecommendationService(self.db).persist_recommendations(
                organization_id=uuid.UUID(str(organization_id)),
                project_id=uuid.UUID(str(project_id)),
                recommendations=recommendations
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
            "forecast_data_source": forecast_data_source,
            "recommendations": recommendations
        }

    async def _resolve_forecast_inputs(
        self,
        organization_id: str,
        project_id: Optional[str],
        historical_velocities: Optional[List[float]],
        remaining_points: Optional[float],
    ) -> "tuple[List[float], float, Dict[str, str]]":
        """Real Monte Carlo inputs (Phase 80) when the caller didn't explicitly supply them:
        real Jira sprint velocity history (Phase 72) and the real sum of remaining
        ProjectTask story points, falling back to the original honest example numbers only
        when neither the caller nor real project data supplies a value. Never raises -- a
        real-data lookup failure (Jira not connected, no tasks, etc.) just falls through to
        the next tier."""
        source = {
            "velocities": "caller" if historical_velocities is not None else "default",
            "remaining_points": "caller" if remaining_points is not None else "default",
        }
        resolved_velocities = historical_velocities
        resolved_points = remaining_points

        if self.db is not None and project_id is not None and (resolved_velocities is None or resolved_points is None):
            try:
                org_uuid = uuid.UUID(str(organization_id))
                proj_uuid = uuid.UUID(str(project_id))

                if resolved_velocities is None:
                    from app.services.integration import IntegrationService
                    try:
                        velocity_data = await IntegrationService(self.db).get_jira_velocity_for_project(org_uuid, proj_uuid)
                        history = velocity_data.get("sprint_velocity_history") or []
                        completed = [s["completed"] for s in history if isinstance(s.get("completed"), (int, float))]
                        if completed:
                            resolved_velocities = completed
                            source["velocities"] = "real"
                    except Exception:
                        pass

                if resolved_points is None:
                    from sqlalchemy import select, func
                    from app.models.project import ProjectTask
                    result = await self.db.execute(
                        select(func.coalesce(func.sum(ProjectTask.story_points), 0)).where(
                            ProjectTask.organization_id == org_uuid,
                            ProjectTask.project_id == proj_uuid,
                            ProjectTask.status != "done",
                        )
                    )
                    total_remaining = result.scalar_one()
                    if total_remaining and total_remaining > 0:
                        resolved_points = float(total_remaining)
                        source["remaining_points"] = "real"
            except Exception:
                pass

        return (
            resolved_velocities if resolved_velocities else [6.0, 7.0, 5.5, 8.0],
            resolved_points if resolved_points is not None else 25.0,
            source,
        )

    async def _execute_real_agent_step(
        self,
        step: PlanStep,
        organization_id: str,
        project_id: Optional[str],
        subgraph_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a plan step's real agent persona (Phase 69) -- reuses the exact same real
        LLM execution path POST /agents/execute already uses (AgentService.execute_agent ->
        BaseAgent._llm_call), rather than the old inline synthetic-string placeholder,
        grounded in real context assembled from the sources already built by earlier phases.
        Never raises -- an agent execution failure becomes a FAILURE-status result the
        Reflection Engine can react to (including triggering a replan), not a crashed pipeline
        run."""
        import uuid as _uuid
        from app.services.agent import AgentService
        from app.services.context_snapshot import ContextSnapshotService
        from app.services.context import ContextEngineService

        task_text = step.input_params.get("task", step.name)
        real_context: Dict[str, Any] = {"subgraph": subgraph_context} if subgraph_context else {}

        try:
            org_uuid = _uuid.UUID(str(organization_id))
            proj_uuid = _uuid.UUID(str(project_id)) if project_id else None

            if proj_uuid:
                try:
                    latest_snapshot = await ContextSnapshotService(self.db).get_latest_snapshot(org_uuid, proj_uuid)
                    if latest_snapshot:
                        real_context["project_snapshot"] = latest_snapshot.state_payload.get("summary")
                except Exception:
                    pass

                try:
                    # rerank=True (Phase 82) -- real LLM relevance pass on top of the real
                    # vector search, same mechanism/fallback as Phase 78. Deliberately turned
                    # on here despite the added per-step LLM call cost (roughly doubling real
                    # LLM calls per agent step), a trade-off flagged in Phase 81 and closed
                    # out on request rather than left silently deferred.
                    search_results = await ContextEngineService(self.db).search_context(
                        organization_id=org_uuid, query_text=task_text, project_id=proj_uuid, top_k=3, rerank=True
                    )
                    if search_results:
                        real_context["relevant_context"] = [r["content"] for r in search_results]
                except Exception:
                    pass

            execution = await AgentService(self.db).execute_agent(
                agent_type=step.target,
                task_input=task_text,
                organization_id=org_uuid,
                project_id=proj_uuid,
                context=real_context,
            )
            return {
                "status": "SUCCESS" if execution.status == "COMPLETED" else "FAILURE",
                "result": execution.output_payload,
                "agent_execution_id": str(execution.id),
            }
        except Exception as e:
            return {
                "status": "FAILURE",
                "error": str(e),
                "result": {"agent": step.target, "task_inputs": step.input_params},
            }
