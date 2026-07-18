from uuid import UUID
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.models.tenant import Workspace

router = APIRouter()

class WorkspaceCreateRequest(BaseModel):
    organization_id: UUID
    name: str = Field(..., min_length=1, max_length=255)

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a workspace under an organization."""
    workspace = Workspace(
        organization_id=payload.organization_id,
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
    organization_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all active workspaces for an organization."""
    res = await db.execute(select(Workspace).where(Workspace.organization_id == organization_id, Workspace.deleted_at == None))
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
