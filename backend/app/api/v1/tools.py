from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.tool import ToolService

router = APIRouter()

class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., description="Registered tool name (e.g. github_create_issue, jira_get_issue)")
    parameters: Dict[str, Any] = Field(default_dict={}, description="Tool parameters payload")
    agent_execution_id: Optional[UUID] = None

@router.get("", status_code=status.HTTP_200_OK)
async def list_tools(db: AsyncSession = Depends(get_db)):
    """List all registered tools, descriptions, and parameter schemas."""
    service = ToolService(db)
    tools = service.list_available_tools()
    return {"tools_count": len(tools), "tools": tools}

@router.post("/execute", status_code=status.HTTP_200_OK)
async def execute_tool(
    payload: ToolExecuteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute a registered tool by name with parameters."""
    service = ToolService(db)
    try:
        result = await service.execute_tool(
            tool_name=payload.tool_name,
            parameters=payload.parameters,
            agent_execution_id=payload.agent_execution_id
        )
        return {
            "status": "success",
            "tool_name": payload.tool_name,
            "output": result
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
