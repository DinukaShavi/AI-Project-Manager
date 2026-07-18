from uuid import UUID
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.project import ProjectTask
from app.analytics.predictor import PredictiveAnalyticsEngine

class AnalyticsService:
    """Service layer connecting database tasks with PredictiveAnalyticsEngine."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_burndown_chart(self, project_id: UUID, total_days: int = 14, elapsed_days: int = 7) -> Dict[str, Any]:
        """Fetch project tasks and compute burndown trajectory."""
        res = await self.db.execute(select(ProjectTask).where(ProjectTask.project_id == project_id, ProjectTask.deleted_at == None))
        tasks = res.scalars().all()

        total_points = sum(t.story_points for t in tasks if t.story_points)
        completed_points = sum(t.story_points for t in tasks if t.status == "done" and t.story_points)

        burndown = PredictiveAnalyticsEngine.calculate_burndown(
            total_points=float(total_points),
            completed_points=float(completed_points),
            total_days=total_days,
            elapsed_days=elapsed_days
        )

        return {
            "project_id": str(project_id),
            "total_story_points": total_points,
            "completed_story_points": completed_points,
            "burndown_trajectory": burndown
        }

    async def predict_completion_forecast(self, project_id: UUID, elapsed_days: int = 7, total_sprint_days: int = 14) -> Dict[str, Any]:
        """Fetch project tasks and compute delivery date prediction & risk score."""
        res = await self.db.execute(select(ProjectTask).where(ProjectTask.project_id == project_id, ProjectTask.deleted_at == None))
        tasks = res.scalars().all()

        total_tasks = len(tasks)
        completed_tasks = len([t for t in tasks if t.status == "done"])
        critical_open = len([t for t in tasks if t.status != "done" and t.priority in ("critical", "high")])
        unassigned = len([t for t in tasks if t.status != "done" and t.assignee_id is None])

        total_points = sum(t.story_points for t in tasks if t.story_points)
        completed_points = sum(t.story_points for t in tasks if t.status == "done" and t.story_points)

        forecast = PredictiveAnalyticsEngine.predict_completion_date(
            total_points=float(total_points),
            completed_points=float(completed_points),
            elapsed_days=elapsed_days,
            total_sprint_days=total_sprint_days
        )

        risk = PredictiveAnalyticsEngine.predict_risk_score(
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            critical_open_tasks=critical_open,
            unassigned_tasks=unassigned
        )

        return {
            "project_id": str(project_id),
            "forecast": forecast,
            "risk_assessment": risk
        }
