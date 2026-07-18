from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.models.project import ProjectTask

router = APIRouter()

@router.get("/sprint", status_code=status.HTTP_200_OK)
async def get_sprint_analytics(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Calculate sprint velocity, story points completion rate, and delivery risk index."""
    res = await db.execute(select(ProjectTask).where(ProjectTask.project_id == project_id, ProjectTask.deleted_at == None))
    tasks = res.scalars().all()

    total_tasks = len(tasks)
    completed_tasks = [t for t in tasks if t.status.lower() == "done"]
    in_progress_tasks = [t for t in tasks if t.status.lower() == "in_progress"]
    todo_tasks = [t for t in tasks if t.status.lower() == "todo"]
    high_risk_tasks = [t for t in tasks if t.priority.lower() in ["high", "critical"] and t.status.lower() != "done"]

    total_points = sum(t.story_points or 0 for t in tasks)
    completed_points = sum(t.story_points or 0 for t in completed_tasks)
    completion_rate = (completed_points / total_points * 100.0) if total_points > 0 else 0.0

    # Risk score index (0.0 to 1.0) based on uncompleted high priority tasks
    risk_score = min(1.0, len(high_risk_tasks) * 0.25)

    return {
        "project_id": str(project_id),
        "total_tasks": total_tasks,
        "completed_tasks": len(completed_tasks),
        "in_progress_tasks": len(in_progress_tasks),
        "todo_tasks": len(todo_tasks),
        "high_risk_open_tasks": len(high_risk_tasks),
        "total_story_points": total_points,
        "completed_story_points": completed_points,
        "completion_rate_percentage": round(completion_rate, 2),
        "delivery_risk_index": round(risk_score, 2),
        "risk_level": "low" if risk_score < 0.3 else ("medium" if risk_score < 0.7 else "high")
    }
