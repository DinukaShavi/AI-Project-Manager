import uuid as uuid_lib
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.core.rbac_pdp import ADMIN_ROLES
from app.models.tenant import User
from app.services.integration import IntegrationService
from app.services.slack_activity import SlackActivityService

router = APIRouter()


class LinkGitHubRepositoryRequest(BaseModel):
    project_id: UUID
    external_repo_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    clone_url: str = Field(..., min_length=1)


class CalendarSyncRequest(BaseModel):
    project_id: UUID
    start_date: datetime
    end_date: datetime


class CreateCalendarEventRequest(BaseModel):
    project_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    start_time: datetime
    end_time: datetime
    attendee_emails: Optional[List[str]] = None
    # Real org members picked from GET /organizations/members/directory (Phase 64) -- resolved
    # to their real emails server-side and merged with attendee_emails, rather than a PM having
    # to type every teammate's exact email by hand.
    attendee_user_ids: Optional[List[UUID]] = None
    description: str = ""


class SlackChannelMappingRequest(BaseModel):
    project_id: UUID
    slack_channel_id: str = Field(..., min_length=1, max_length=50)


# NOTE: the four provider webhook intake routes formerly lived here as
# POST /{provider}/webhook?organization_id=&secret= -- both organization_id and secret were
# client-supplied query parameters with no verification the caller had any relationship to
# that organization, which let a forged-but-self-signed request inject events into any org's
# stream (Phase 60). They have been replaced entirely by the per-organization,
# unguessable-token routes in app/api/v1/webhooks.py: POST /webhooks/{provider}/{webhook_token}.
# The endpoint below lets an org admin discover their own real webhook URL to configure on the
# provider's side.


@router.get("/{provider}/webhook-url", status_code=status.HTTP_200_OK)
async def get_webhook_url(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return this organization's real, token-bearing inbound webhook URL for a connected
    provider, so an admin can paste it into GitHub/Jira/Slack/Google's webhook configuration.
    OrgAdmin/SuperAdmin only, tenant-scoped from the authenticated user -- never derived from
    a client-supplied organization_id."""
    role_names = {r.name for r in current_user.roles}
    if not role_names & ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OrgAdmin or SuperAdmin roles may view the webhook URL."
        )

    service = IntegrationService(db)
    path = await service.get_webhook_url(current_user.organization_id, provider)
    if not path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{provider}' is not connected for this organization yet."
        )
    return {"provider": provider.lower(), "webhook_path": path}


@router.get("/oauth/{provider}/authorize", status_code=status.HTTP_200_OK)
async def oauth_authorize(
    provider: str,
    redirect_uri: Optional[str] = "http://localhost:3000/oauth/callback",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate third-party OAuth provider authorization URL for the authenticated user's organization."""
    service = IntegrationService(db)
    try:
        url = await service.generate_oauth_authorize_url(
            provider=provider,
            organization_id=current_user.organization_id,
            redirect_uri=redirect_uri or "http://localhost:3000/oauth/callback"
        )
        return {"authorization_url": url, "provider": provider, "organization_id": str(current_user.organization_id)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/oauth/{provider}/callback", status_code=status.HTTP_200_OK)
async def oauth_callback(
    provider: str,
    code: str,
    redirect_uri: Optional[str] = "http://localhost:3000/oauth/callback",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exchange OAuth authorization code for encrypted tokens and persist for the authenticated user's organization."""
    service = IntegrationService(db)
    try:
        res = await service.exchange_code_for_token(
            provider=provider,
            code=code,
            organization_id=current_user.organization_id,
            redirect_uri=redirect_uri or "http://localhost:3000/oauth/callback",
            user_id=current_user.id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/oauth/tokens/{organization_id}", status_code=status.HTTP_200_OK)
async def get_tenant_oauth_token(
    organization_id: UUID,
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve active decrypted tenant access token for tool invocation."""
    if organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access another organization's OAuth tokens.")
    service = IntegrationService(db)
    try:
        token = await service.get_valid_oauth_token(organization_id=organization_id, provider=provider)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active OAuth token found for provider '{provider}'.")
    return {"organization_id": str(organization_id), "provider": provider, "access_token": token}


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_integration_statuses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Connection Center dashboard status (implementation_roadmap.md Milestone 6). Initial
    state for the frontend to render before any live WebSocket update arrives; org is
    always the authenticated caller's own, never client-supplied. Never returns token
    material -- use GET /oauth/tokens/{organization_id} for actual credential retrieval."""
    service = IntegrationService(db)
    statuses = await service.get_integration_statuses(current_user.organization_id)
    return {"organization_id": str(current_user.organization_id), "integrations": statuses}


@router.delete("/oauth/{provider}", status_code=status.HTTP_200_OK)
async def revoke_oauth_integration(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke and deactivate the authenticated user's organization's OAuth provider integration."""
    service = IntegrationService(db)
    success = await service.revoke_oauth_token(organization_id=current_user.organization_id, provider=provider, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found.")
    return {"status": "revoked", "provider": provider, "organization_id": str(current_user.organization_id)}


@router.post("/github/repositories", status_code=status.HTTP_201_CREATED)
async def link_github_repository(
    payload: LinkGitHubRepositoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link a GitHub repository to a project, per api_contract.md section 4.A. This is the
    prerequisite the documented GitHub backup-sync cron needs to know which repositories to poll."""
    service = IntegrationService(db)
    try:
        repo = await service.link_github_repository(
            organization_id=current_user.organization_id,
            project_id=payload.project_id,
            external_repo_id=payload.external_repo_id,
            name=payload.name,
            clone_url=payload.clone_url,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {
        "id": str(repo.id),
        "project_id": str(repo.project_id),
        "external_repo_id": repo.external_repo_id,
        "name": repo.name,
        "clone_url": repo.clone_url,
        "status": "linked"
    }


@router.get("/github/discover-repositories", status_code=status.HTTP_200_OK)
async def discover_github_repositories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List real repositories the authenticated user's organization's connected GitHub token
    can access, for the "select GitHub repositories to link" step (api_contract.md section
    4.A). Real GitHub API call via the stored OAuth token (the formerly-hardcoded GET
    /github/repositories mock was retired in Phase 67, superseded by this endpoint)."""
    service = IntegrationService(db)
    try:
        repos = await service.discover_github_repositories(current_user.organization_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"total_repositories": len(repos), "repositories": repos}


@router.get("/github/linked-repositories", status_code=status.HTTP_200_OK)
async def list_linked_github_repositories(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List repositories already linked to a project via POST /github/repositories. Real,
    project-scoped, tenant-isolated -- reads the actual `repositories` table."""
    service = IntegrationService(db)
    try:
        repos = await service.list_linked_repositories(current_user.organization_id, project_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {
        "project_id": str(project_id),
        "total_repositories": len(repos),
        "repositories": [
            {"id": str(r.id), "external_repo_id": r.external_repo_id, "name": r.name, "clone_url": r.clone_url}
            for r in repos
        ],
    }


async def _verify_project_ownership_for_dashboard(db: AsyncSession, project_id: UUID, organization_id: UUID) -> None:
    """Shared tenant-ownership guard for the real GitHub dashboard reads below (matches
    context.py's identical pattern) -- without this, any authenticated user could probe
    another organization's project data by guessing a project_id."""
    from app.models.project import Project
    from sqlalchemy import select as _select
    res = await db.execute(
        _select(Project).where(Project.id == project_id, Project.organization_id == organization_id, Project.deleted_at == None)
    )
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found in this organization.")


@router.get("/github/pull-requests", status_code=status.HTTP_200_OK)
async def get_github_pull_requests(
    project_id: UUID,
    repository: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve real pull requests across a project's linked GitHub repositories."""
    await _verify_project_ownership_for_dashboard(db, project_id, current_user.organization_id)
    service = IntegrationService(db)
    try:
        pull_requests = await service.get_pull_requests_for_org(current_user.organization_id, project_id, repository)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "total_pull_requests": len(pull_requests),
        "pull_requests": pull_requests,
    }


@router.get("/github/commits", status_code=status.HTTP_200_OK)
async def get_github_commits(
    project_id: UUID,
    repository: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve real commit history across a project's linked GitHub repositories."""
    await _verify_project_ownership_for_dashboard(db, project_id, current_user.organization_id)
    service = IntegrationService(db)
    try:
        commits = await service.get_commits_for_org(current_user.organization_id, project_id, repository)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "total_commits": len(commits),
        "commits": commits,
    }


@router.get("/github/issues", status_code=status.HTTP_200_OK)
async def get_github_issues(
    project_id: UUID,
    repository: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve real issues across a project's linked GitHub repositories."""
    await _verify_project_ownership_for_dashboard(db, project_id, current_user.organization_id)
    service = IntegrationService(db)
    try:
        issues = await service.get_issues_for_org(current_user.organization_id, project_id, repository)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "total_issues": len(issues),
        "issues": issues,
    }


# ============================================================================
# JIRA PLATFORM INTEGRATION MODULE ENDPOINTS
# ============================================================================

@router.get("/jira/projects", status_code=status.HTTP_200_OK)
async def get_jira_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Import Jira Projects List, per api_contract.md section 5.A. Requires
    authentication (unlike the previous unauthenticated mock) since it now calls the real
    Jira REST API using this deployment's configured credentials."""
    import httpx

    service = IntegrationService(db)
    try:
        projects = await service.get_jira_projects()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Jira API returned an error ({e.response.status_code}).")
    except httpx.RequestError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Jira API is currently unreachable. Please try again shortly.")
    return {"projects": projects}


@router.get("/jira/issues", status_code=status.HTTP_200_OK)
async def get_jira_issues(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the real Jira issue backlog for a project, via the org's per-organization
    OAuth connection (Phase 62 -- the follow-up to Phase 55's site/identity resolution)."""
    await _verify_project_ownership_for_dashboard(db, project_id, current_user.organization_id)
    service = IntegrationService(db)
    try:
        issues = await service.get_jira_issues_for_project(current_user.organization_id, project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "total_issues": len(issues),
        "issues": issues,
    }


@router.get("/jira/sprints", status_code=status.HTTP_200_OK)
async def get_jira_sprints(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the real Jira sprints for a project's board, via the org's per-organization
    OAuth connection (Phase 62)."""
    await _verify_project_ownership_for_dashboard(db, project_id, current_user.organization_id)
    service = IntegrationService(db)
    try:
        sprints = await service.get_jira_sprints_for_project(current_user.organization_id, project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "total_sprints": len(sprints),
        "sprints": sprints,
    }


@router.get("/jira/workload", status_code=status.HTTP_200_OK)
async def get_jira_workload(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the real per-assignee story points distribution for a project (Phase 72),
    aggregated from the same real Jira issues /jira/issues already returns."""
    await _verify_project_ownership_for_dashboard(db, project_id, current_user.organization_id)
    service = IntegrationService(db)
    try:
        workload = await service.get_jira_workload_for_project(current_user.organization_id, project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "team_workload": workload,
    }


@router.get("/jira/velocity", status_code=status.HTTP_200_OK)
async def get_jira_velocity(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve real historical sprint velocity for a project (Phase 72), reconstructed from
    real per-sprint story points (/jira/sprints's own data) since Jira has no public Velocity
    Chart REST endpoint."""
    await _verify_project_ownership_for_dashboard(db, project_id, current_user.organization_id)
    service = IntegrationService(db)
    try:
        velocity = await service.get_jira_velocity_for_project(current_user.organization_id, project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        **velocity,
    }


# ============================================================================
# SLACK PLATFORM INTEGRATION MODULE ENDPOINTS
# ============================================================================

@router.post("/slack/mappings", status_code=status.HTTP_200_OK)
async def map_slack_channel(
    payload: SlackChannelMappingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Map Project to Slack Channel, per api_contract.md section 6.A. Lets incoming Slack
    webhook messages be auto-routed to the correct project by channel."""
    service = IntegrationService(db)
    try:
        mapping = await service.map_slack_channel_to_project(
            organization_id=current_user.organization_id,
            project_id=payload.project_id,
            slack_channel_id=payload.slack_channel_id,
            user_id=current_user.id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return {
        "id": str(mapping.id),
        "project_id": str(mapping.project_id),
        "slack_channel_id": mapping.slack_channel_id,
        "status": "mapped"
    }


@router.get("/slack/discover-channels", status_code=status.HTTP_200_OK)
async def discover_slack_channels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List real channels the authenticated user's organization's connected Slack bot token
    can see, for the "select Slack channels to map" step (api_contract.md section 6.A). Real
    Slack API call via the stored OAuth token (the formerly-hardcoded GET /slack/channels mock
    was retired in Phase 67, superseded by this endpoint)."""
    service = IntegrationService(db)
    try:
        channels = await service.discover_slack_channels(current_user.organization_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"total_channels": len(channels), "channels": channels}


@router.get("/slack/mapped-channels", status_code=status.HTTP_200_OK)
async def list_mapped_slack_channels(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List Slack channels already mapped to a project via POST /slack/mappings. Real,
    project-scoped, tenant-isolated -- reads the actual `slack_channel_mappings` table."""
    service = IntegrationService(db)
    try:
        mappings = await service.list_mapped_channels(current_user.organization_id, project_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {
        "project_id": str(project_id),
        "total_channels": len(mappings),
        "channels": [{"id": str(m.id), "slack_channel_id": m.slack_channel_id} for m in mappings],
    }


@router.get("/slack/messages", status_code=status.HTTP_200_OK)
async def get_slack_messages(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve real recent messages for a channel already mapped to one of this org's
    projects (Phase 63), via the org's real Slack bot token."""
    service = IntegrationService(db)
    try:
        messages = await service.get_slack_messages_for_channel(current_user.organization_id, channel_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "channel_id": channel_id,
        "total_messages": len(messages),
        "messages": messages,
    }


@router.get("/slack/users", status_code=status.HTTP_200_OK)
async def get_slack_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve real active Slack workspace team members (Phase 63), via the org's real Slack
    bot token. Org-wide -- workspace membership isn't a per-project concept."""
    service = IntegrationService(db)
    try:
        users = await service.get_slack_users_for_org(current_user.organization_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "total_users": len(users),
        "users": users,
    }


@router.get("/slack/activity", status_code=status.HTTP_200_OK)
async def get_slack_activity_analysis(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve real activity analytics for a channel already mapped to one of this org's
    projects (Phase 72). `activity_by_hour`/`message_count` are computed directly from real
    message timestamps; `sentiment_score`/`top_discussed_topics` come from a real LLM call over
    the real message text, honestly None/[] rather than fabricated when unavailable."""
    service = IntegrationService(db)
    try:
        messages = await service.get_slack_messages_for_channel(current_user.organization_id, channel_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    activity_service = SlackActivityService()
    sentiment = await activity_service.analyze_sentiment_and_topics(messages)
    return {
        "organization_id": str(current_user.organization_id),
        "channel_id": channel_id,
        "message_count": len(messages),
        "activity_by_hour": activity_service.compute_activity_by_hour(messages),
        **sentiment,
    }


# ============================================================================
# GOOGLE CALENDAR PLATFORM INTEGRATION MODULE ENDPOINTS
# ============================================================================

@router.post("/calendar/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_calendar_events(
    payload: CalendarSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Sync Calendar Events Range, per api_contract.md section 7.A. Calendar is documented as
    polling-driven (no webhook-driven real-time path), so this is the primary way real Google
    Calendar event data ever enters the system. Runs synchronously within the request (this
    codebase has no Celery/task-queue system to hand off to) but returns a sync task token per
    the documented 202 Accepted response shape."""
    service = IntegrationService(db)
    try:
        result = await service.sync_calendar_events(
            organization_id=current_user.organization_id,
            project_id=payload.project_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "sync_task_id": str(uuid_lib.uuid4()),
        "status": "completed",
        "project_id": str(payload.project_id),
        "events_synced": result["events_synced"],
        "events_found": result["events_found"],
    }


@router.post("/calendar/meetings", status_code=status.HTTP_201_CREATED)
async def create_calendar_meeting(
    payload: CreateCalendarEventRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Schedule a real Google Calendar event -- the write side POST /calendar/sync never had.
    Uses the org's existing calendar.events OAuth grant (already covers write, no new consent
    needed). The created Meeting appears immediately in GET /calendar/meetings, not just after
    the next poll."""
    service = IntegrationService(db)
    try:
        meeting = await service.create_calendar_event(
            organization_id=current_user.organization_id,
            project_id=payload.project_id,
            title=payload.title,
            start_time=payload.start_time,
            end_time=payload.end_time,
            attendee_emails=payload.attendee_emails,
            attendee_user_ids=payload.attendee_user_ids,
            description=payload.description,
            user_id=current_user.id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "id": str(meeting.id),
        "external_event_id": meeting.external_event_id,
        "title": meeting.title,
        "start_time": meeting.start_time.isoformat(),
        "end_time": meeting.end_time.isoformat(),
        "attendees": meeting.attendees,
        "meet_link": meeting.meet_link,
    }


@router.get("/calendar/meetings", status_code=status.HTTP_200_OK)
async def list_calendar_meetings(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List Synced Calendar Meetings for a project (database_schema_design.md section 19,
    ui_ux_design.md section 10 Calendar page). Reads the real Meeting rows written by
    POST /calendar/sync, including each meeting's real Google Meet link when it has one
    (Phase 65)."""
    service = IntegrationService(db)
    try:
        meetings = await service.list_meetings(
            organization_id=current_user.organization_id,
            project_id=project_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {
        "project_id": str(project_id),
        "total_meetings": len(meetings),
        "meetings": [
            {
                "id": str(m.id),
                "external_event_id": m.external_event_id,
                "title": m.title,
                "start_time": m.start_time.isoformat(),
                "end_time": m.end_time.isoformat(),
                "attendees": m.attendees,
                "meet_link": m.meet_link,
            }
            for m in meetings
        ],
    }


@router.get("/calendar/availability", status_code=status.HTTP_200_OK)
async def get_calendar_availability(
    start_date: datetime,
    end_date: datetime,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Real team availability across the org's real members (Phase 65), via Google Calendar's
    freeBusy.query API -- replaces the mock GET /google/availability."""
    service = IntegrationService(db)
    try:
        slots = await service.get_team_availability(current_user.organization_id, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(current_user.organization_id),
        "available_slots": slots,
    }


# GET /google/events was removed here (Phase 67) -- dead code, no frontend caller since the
# real GET /calendar/meetings (Phase 50/56) covers the same real synced-events concept.
# GET /google/meetings and GET /google/availability were removed here (Phase 65) -- both are
# now real: GET /calendar/meetings includes each meeting's real meet_link, and
# GET /calendar/availability computes real availability from Google's freeBusy.query API.



