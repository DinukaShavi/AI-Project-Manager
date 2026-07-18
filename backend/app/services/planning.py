from typing import Any, Dict, Optional, Tuple
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent import AgentPlan
from app.planning.planner import HTNPlanner
from app.services.workflow import WorkflowService
from app.models.workflow import WorkflowExecution

class PlanningService:
    def __init__(self, session: AsyncSession):
        """Planning Service managing HTN goal decomposition, database plan persistence, and execution."""
        self.session = session
        self.planner = HTNPlanner()
        self.workflow_service = WorkflowService(session)

    async def generate_plan(
        self,
        goal: str,
        organization_id: UUID,
        project_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentPlan:
        """Decompose high-level goal into HTN plan steps and persist in agent_plans table."""
        steps = self.planner.decompose_goal(goal, context)
        plan_dict = [step.to_dict() for step in steps]

        plan = AgentPlan(
            organization_id=organization_id,
            project_id=project_id,
            goal=goal,
            status="generated",
            plan_steps=plan_dict
        )
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        return plan

    async def execute_plan(
        self,
        plan_id: Optional[UUID] = None,
        goal: Optional[str] = None,
        organization_id: Optional[UUID] = None,
        project_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[AgentPlan, WorkflowExecution]:
        """Decompose or fetch an HTN goal plan and execute its WorkflowDAG."""
        plan = None
        if plan_id:
            res = await self.session.execute(select(AgentPlan).where(AgentPlan.id == plan_id))
            plan = res.scalar_one_or_none()
            if not plan:
                raise ValueError(f"Plan ID '{plan_id}' not found.")
        elif goal and organization_id:
            plan = await self.generate_plan(goal, organization_id, project_id, context)
        else:
            raise ValueError("Must specify either plan_id or both goal and organization_id.")

        # Reconstruct WorkflowDAG from plan steps
        from app.planning.planner import PlanStep
        steps = [PlanStep(**s) for s in plan.plan_steps]
        dag = self.planner.build_dag_from_plan(steps)

        # Update status to executing
        plan.status = "executing"
        await self.session.commit()

        try:
            execution = await self.workflow_service.execute_workflow(
                dag=dag,
                organization_id=plan.organization_id,
                project_id=plan.project_id,
                initial_context=context
            )
            plan.status = "executed"
            await self.session.commit()
            return plan, execution
        except Exception as e:
            plan.status = "failed"
            await self.session.commit()
            raise e

    async def get_plan(self, plan_id: UUID) -> Optional[AgentPlan]:
        """Fetch plan record by ID."""
        res = await self.session.execute(select(AgentPlan).where(AgentPlan.id == plan_id))
        return res.scalar_one_or_none()
