from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectTask
from app.services.external_identity import ExternalIdentityService

# Jira's status field always nests a statusCategory.key in this fixed, small set regardless
# of a project's custom workflow status *names* -- the same category
# get_sprint_story_points (Phase 62) already keys off for "is this issue done".
STATUS_CATEGORY_MAP = {
    "new": "todo",
    "indeterminate": "in_progress",
    "done": "done",
}


class JiraTaskSyncService:
    """Real one-way Jira issue -> ProjectTask sync (Phase 76): Jira is the source of truth.
    A real Jira issue (webhook or backup-sync) auto-creates or updates a matching
    ProjectTask's title/status/assignee; edits to the ProjectTask itself never push back to
    Jira. Called from ContextIngestionService.handle_event, the same choke point every real
    Jira event already passes through."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.identity_service = ExternalIdentityService(session)

    async def sync_task_from_issue(
        self,
        organization_id: UUID,
        project_id: UUID,
        issue_key: str,
        summary: str,
        status_category: Optional[str],
        assignee_account_id: Optional[str],
    ) -> Optional[ProjectTask]:
        if not issue_key or not summary:
            return None

        res = await self.session.execute(
            select(ProjectTask).where(
                ProjectTask.organization_id == organization_id,
                ProjectTask.project_id == project_id,
                ProjectTask.jira_issue_key == issue_key,
            )
        )
        task = res.scalar_one_or_none()

        assignee_id = None
        if assignee_account_id:
            assignee_id = await self.identity_service.resolve_user_by_external_account(
                organization_id, "jira", assignee_account_id
            )

        mapped_status = STATUS_CATEGORY_MAP.get(status_category or "")

        if task:
            task.title = summary
            task.assignee_id = assignee_id
            if mapped_status:
                # Only overwrite on real category data -- never downgrade a task's status to
                # a guess when the category is unavailable (e.g. an older backup-sync event
                # from before this phase's pass-through fix).
                task.status = mapped_status
        else:
            task = ProjectTask(
                organization_id=organization_id,
                project_id=project_id,
                title=summary,
                status=mapped_status or "todo",
                assignee_id=assignee_id,
                jira_issue_key=issue_key,
            )
            self.session.add(task)

        await self.session.flush()
        return task
