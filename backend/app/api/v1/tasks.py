from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.models.project import ProjectTask

router = APIRouter()

class TaskCreateRequest(BaseModel):
    project_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = Field("todo", description="'todo', 'in_progress', 'review', 'done'")
    priority: str = Field("medium", description="'low', 'medium', 'high', 'critical'")
    assignee_id: Optional[UUID] = None
    jira_issue_key: Optional[str] = None
    story_points: Optional[int] = 1

class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[UUID] = None
    story_points: Optional[int] = None

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a project task/issue."""
    task = ProjectTask(
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        jira_issue_key=payload.jira_issue_key,
        story_points=payload.story_points
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {
        "task_id": str(task.id),
        "project_id": str(task.project_id),
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "jira_issue_key": task.jira_issue_key,
        "story_points": task.story_points
    }

@router.get("", status_code=status.HTTP_200_OK)
async def list_tasks(
    project_id: UUID,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all tasks in a project."""
    query = select(ProjectTask).where(ProjectTask.project_id == project_id, ProjectTask.deleted_at == None)
    if status_filter:
        query = query.where(ProjectTask.status == status_filter)

    res = await db.execute(query)
    tasks = res.scalars().all()
    return {
        "tasks_count": len(tasks),
        "tasks": [
            {
                "task_id": str(t.id),
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "assignee_id": str(t.assignee_id) if t.assignee_id else None,
                "jira_issue_key": t.jira_issue_key,
                "story_points": t.story_points
            }
            for t in tasks
        ]
    }

@router.put("/{task_id}", status_code=status.HTTP_200_OK)
async def update_task(
    task_id: UUID,
    payload: TaskUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update task attributes (status, assignee, priority, points)."""
    res = await db.execute(select(ProjectTask).where(ProjectTask.id == task_id, ProjectTask.deleted_at == None))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if payload.title is not None:
        task.title = payload.title
    if payload.description is not None:
        task.description = payload.description
    if payload.status is not None:
        task.status = payload.status
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.assignee_id is not None:
        task.assignee_id = payload.assignee_id
    if payload.story_points is not None:
        task.story_points = payload.story_points

    await db.commit()
    await db.refresh(task)
    return {
        "task_id": str(task.id),
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        "story_points": task.story_points
    }
