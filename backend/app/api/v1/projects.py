from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.project import Project
from app.models.tenant import User, Workspace

router = APIRouter()

class ProjectCreateRequest(BaseModel):
    workspace_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    jira_project_key: Optional[str] = None
    github_repo_name: Optional[str] = None

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new project within a workspace owned by the authenticated user's organization."""
    ws_res = await db.execute(
        select(Workspace).where(Workspace.id == payload.workspace_id, Workspace.organization_id == current_user.organization_id)
    )
    if not ws_res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found in this organization.")

    project = Project(
        organization_id=current_user.organization_id,
        workspace_id=payload.workspace_id,
        name=payload.name,
        description=payload.description,
        jira_project_key=payload.jira_project_key,
        github_repo_name=payload.github_repo_name
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return {
        "project_id": str(project.id),
        "name": project.name,
        "workspace_id": str(project.workspace_id),
        "jira_project_key": project.jira_project_key,
        "github_repo_name": project.github_repo_name
    }

@router.get("", status_code=status.HTTP_200_OK)
async def list_projects(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all active projects in a workspace owned by the authenticated user's organization."""
    ws_res = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.organization_id == current_user.organization_id)
    )
    if not ws_res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found in this organization.")

    res = await db.execute(
        select(Project).where(
            Project.workspace_id == workspace_id,
            Project.organization_id == current_user.organization_id,
            Project.deleted_at == None,
        )
    )
    projects = res.scalars().all()
    return {
        "projects_count": len(projects),
        "projects": [
            {
                "project_id": str(p.id),
                "name": p.name,
                "description": p.description,
                "jira_project_key": p.jira_project_key,
                "github_repo_name": p.github_repo_name
            }
            for p in projects
        ]
    }

@router.get("/{project_id}", status_code=status.HTTP_200_OK)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve project details by ID, scoped to the authenticated user's organization."""
    res = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
            Project.deleted_at == None,
        )
    )
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return {
        "project_id": str(project.id),
        "name": project.name,
        "description": project.description,
        "workspace_id": str(project.workspace_id),
        "jira_project_key": project.jira_project_key,
        "github_repo_name": project.github_repo_name,
        "created_at": project.created_at
    }
