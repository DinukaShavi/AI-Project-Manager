from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.planning import PlanningService

router = APIRouter()

class PlanGenerateRequest(BaseModel):
    organization_id: UUID
    goal: str = Field(..., description="High-level project goal or milestone description")
    project_id: Optional[UUID] = None
    context: Optional[Dict[str, Any]] = None

class PlanExecuteRequest(BaseModel):
    organization_id: Optional[UUID] = None
    goal: Optional[str] = Field(None, description="Goal to plan and execute")
    plan_id: Optional[UUID] = Field(None, description="Existing plan ID to execute")
    project_id: Optional[UUID] = None
    context: Optional[Dict[str, Any]] = None

@router.post("/plan", status_code=status.HTTP_201_CREATED)
async def generate_plan(
    payload: PlanGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Decompose high-level goal into HTN plan steps without immediate execution."""
    service = PlanningService(db)
    plan = await service.generate_plan(
        goal=payload.goal,
        organization_id=payload.organization_id,
        project_id=payload.project_id,
        context=payload.context
    )
    return {
        "plan_id": str(plan.id),
        "goal": plan.goal,
        "status": plan.status,
        "steps_count": len(plan.plan_steps),
        "plan_steps": plan.plan_steps
    }

@router.post("/execute", status_code=status.HTTP_200_OK)
async def execute_plan(
    payload: PlanExecuteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Decompose a high-level goal into an HTN plan and immediately execute its WorkflowDAG."""
    service = PlanningService(db)
    try:
        plan, execution = await service.execute_plan(
            plan_id=payload.plan_id,
            goal=payload.goal,
            organization_id=payload.organization_id,
            project_id=payload.project_id,
            context=payload.context
        )
        return {
            "plan_id": str(plan.id),
            "goal": plan.goal,
            "plan_status": plan.status,
            "execution_id": str(execution.id),
            "execution_status": execution.status,
            "state": execution.state_payload
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/plans/{plan_id}", status_code=status.HTTP_200_OK)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve HTN plan details by ID."""
    service = PlanningService(db)
    plan = await service.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return {
        "plan_id": str(plan.id),
        "goal": plan.goal,
        "status": plan.status,
        "plan_steps": plan.plan_steps
    }
