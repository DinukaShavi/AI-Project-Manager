from uuid import UUID
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import Workspace, User

router = APIRouter()

class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a workspace under the authenticated user's organization."""
    workspace = Workspace(
        organization_id=current_user.organization_id,
        name=payload.name
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return {
        "workspace_id": str(workspace.id),
        "name": workspace.name,
        "organization_id": str(workspace.organization_id)
    }

@router.get("", status_code=status.HTTP_200_OK)
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all active workspaces for the authenticated user's organization."""
    res = await db.execute(select(Workspace).where(Workspace.organization_id == current_user.organization_id, Workspace.deleted_at == None))
    workspaces = res.scalars().all()
    return {
        "workspaces_count": len(workspaces),
        "workspaces": [
            {
                "workspace_id": str(w.id),
                "name": w.name,
                "organization_id": str(w.organization_id)
            }
            for w in workspaces
        ]
    }
