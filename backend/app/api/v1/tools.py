from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import User
from app.services.tool import ToolService
from app.tools.executor import ToolExecutor

router = APIRouter()

class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., description="Registered tool name (e.g. github_create_issue, jira_get_issue)")
    parameters: Dict[str, Any] = Field(default_dict={}, description="Tool parameters payload")
    agent_execution_id: Optional[UUID] = None
    approval_token: Optional[str] = Field(None, description="Human approval token authorizing a high-risk side-effect tool call")

@router.get("", status_code=status.HTTP_200_OK)
async def list_tools(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all registered tools, descriptions, and parameter schemas."""
    service = ToolService(db)
    tools = service.list_available_tools()
    return {"tools_count": len(tools), "tools": tools}

@router.post("/execute", status_code=status.HTTP_200_OK)
async def execute_tool(
    payload: ToolExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute a registered tool by name, enforcing RBAC permissions and HITL approval
    gating for high-risk side-effect tools via ToolExecutor (Policy Decision Point +
    approval-suspension), rather than invoking ToolService directly and unguarded."""
    executor = ToolExecutor()
    user_role = current_user.roles[0].name if current_user.roles else "Developer"
    try:
        result = await executor.execute_tool(
            tool_name=payload.tool_name,
            parameters=payload.parameters,
            user_role=user_role,
            approval_token=payload.approval_token,
            agent_execution_id=str(payload.agent_execution_id) if payload.agent_execution_id else None,
            db=db,
            organization_id=current_user.organization_id,
            user_id=current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if result["status"] == "PERMISSION_DENIED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result["error"])
    if result["status"] == "TOOL_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    if result["status"] == "VALIDATION_FAILED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    if result["status"] == "WAITING_APPROVAL":
        return {
            "status": "waiting_approval",
            "tool_name": payload.tool_name,
            "approval_id": result["approval_id"],
            "message": result["message"]
        }

    return {
        "status": "success" if result["status"] == "SUCCESS" else "error",
        "tool_name": payload.tool_name,
        "output": result["result"]
    }
