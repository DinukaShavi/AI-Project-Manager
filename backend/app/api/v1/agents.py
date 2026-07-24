from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.agent import AgentService

router = APIRouter()

class AgentExecuteRequest(BaseModel):
    agent_type: str = Field(..., description="Agent persona type: tpm, code_analyst, risk_manager, architect")
    task: str = Field(..., description="Task description or prompt for the agent")
    organization_id: UUID
    project_id: Optional[UUID] = None
    context: Optional[Dict[str, Any]] = None

@router.post("/execute", status_code=status.HTTP_200_OK)
async def execute_agent(
    payload: AgentExecuteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute a specialized AI agent persona and return structured findings."""
    service = AgentService(db)
    try:
        execution = await service.execute_agent(
            agent_type=payload.agent_type,
            task_input=payload.task,
            organization_id=payload.organization_id,
            project_id=payload.project_id,
            context=payload.context
        )
        return {
            "execution_id": str(execution.id),
            "agent_name": execution.agent_name,
            "agent_role": execution.agent_role,
            "status": execution.status,
            "execution_time_ms": execution.execution_time_ms,
            "output": execution.output_payload
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve agent execution log by ID."""
    service = AgentService(db)
    execution = await service.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution record not found")
    return {
        "execution_id": str(execution.id),
        "agent_name": execution.agent_name,
        "agent_role": execution.agent_role,
        "status": execution.status,
        "execution_time_ms": execution.execution_time_ms,
        "input": execution.input_payload,
        "output": execution.output_payload,
        "created_at": execution.created_at
    }


class StateTransitionRequest(BaseModel):
    target_state: str = Field(..., description="Target State Machine Enum: CREATED, QUEUED, PLANNING, EXECUTING, WAITING_TOOL, WAITING_APPROVAL, REFLECTION, RETRYING, COMPLETED, CANCELLED, FAILED")
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@router.post("/executions/{execution_id}/transition", status_code=status.HTTP_200_OK)
async def transition_agent_state(
    execution_id: UUID,
    payload: StateTransitionRequest,
    db: AsyncSession = Depends(get_db)
):
    """Trigger valid State Machine transition for an active agent execution."""
    service = AgentService(db)
    execution = await service.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent execution not found.")

    from app.agents.state_machine import AgentStateMachine, AgentState
    try:
        current_st = AgentState(execution.status.upper())
    except Exception:
        current_st = AgentState.CREATED

    sm = AgentStateMachine(
        execution_id=execution.id,
        agent_name=execution.agent_name,
        initial_status=current_st,
        organization_id=execution.organization_id,
        db_session=db
    )

    try:
        record = await sm.transition_to(
            target_state=AgentState(payload.target_state.upper()),
            reason=payload.reason,
            metadata=payload.metadata
        )
        return record
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

