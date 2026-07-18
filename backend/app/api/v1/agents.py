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
