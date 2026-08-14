import json
import uuid as uuid_lib
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.models.tenant import User
from app.services.integration import IntegrationService

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
    description: str = ""


class SlackChannelMappingRequest(BaseModel):
    project_id: UUID
    slack_channel_id: str = Field(..., min_length=1, max_length=50)

DEFAULT_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")


@router.post("/github/webhook", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    organization_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    secret: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Receive and ingest incoming GitHub webhooks into system events."""
    raw_body = await request.body()
    try:
        json_body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        json_body = {}

    headers = {k.lower(): v for k, v in request.headers.items()}
    service = IntegrationService(db)
    org_id = organization_id or DEFAULT_ORG_ID
    webhook_secret = secret or settings.GITHUB_WEBHOOK_SECRET

    try:
        event = await service.receive_webhook(
            provider="github",
            payload_bytes=raw_body,
            payload_json=json_body,
            headers=headers,
            organization_id=org_id,
            project_id=project_id,
            secret=webhook_secret
        )
        return {"status": "accepted", "event_id": str(event.id), "routing_key": event.routing_key}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/jira/webhook", status_code=status.HTTP_202_ACCEPTED)
async def jira_webhook(
    request: Request,
    organization_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    secret: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Receive and ingest incoming Jira webhooks into system events."""
    raw_body = await request.body()
    try:
        json_body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        json_body = {}

    headers = {k.lower(): v for k, v in request.headers.items()}
    service = IntegrationService(db)
    org_id = organization_id or DEFAULT_ORG_ID
    webhook_secret = secret or settings.JIRA_API_TOKEN

    try:
        event = await service.receive_webhook(
            provider="jira",
            payload_bytes=raw_body,
            payload_json=json_body,
            headers=headers,
            organization_id=org_id,
            project_id=project_id,
            secret=webhook_secret
        )
        return {"status": "accepted", "event_id": str(event.id), "routing_key": event.routing_key}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/slack/webhook")
async def slack_webhook(
    request: Request,
    organization_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    secret: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Receive and ingest incoming Slack Events API webhooks."""
    raw_body = await request.body()
    try:
        json_body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        json_body = {}

    # Handle Slack URL verification challenge immediately
    if json_body.get("type") == "url_verification":
        return Response(content=json_body.get("challenge", ""), media_type="text/plain")

    headers = {k.lower(): v for k, v in request.headers.items()}
    service = IntegrationService(db)
    org_id = organization_id or DEFAULT_ORG_ID
    webhook_secret = secret or settings.SLACK_SIGNING_SECRET

    try:
        event = await service.receive_webhook(
            provider="slack",
            payload_bytes=raw_body,
            payload_json=json_body,
            headers=headers,
            organization_id=org_id,
            project_id=project_id,
            secret=webhook_secret
        )
        return {"status": "accepted", "event_id": str(event.id), "routing_key": event.routing_key}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/google/webhook", status_code=status.HTTP_202_ACCEPTED)
async def google_calendar_webhook(
    request: Request,
    organization_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    secret: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Receive and ingest incoming Google Calendar Push Notifications."""
    raw_body = await request.body()
    try:
        json_body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        json_body = {}

    headers = {k.lower(): v for k, v in request.headers.items()}
    service = IntegrationService(db)
    org_id = organization_id or DEFAULT_ORG_ID
    webhook_secret = secret or settings.GOOGLE_CLIENT_SECRET

    try:
        event = await service.receive_webhook(
            provider="google_calendar",
            payload_bytes=raw_body,
            payload_json=json_body,
            headers=headers,
            organization_id=org_id,
            project_id=project_id,
            secret=webhook_secret
        )
        return {"status": "accepted", "event_id": str(event.id), "routing_key": event.routing_key}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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
    4.A). Real GitHub API call via the stored OAuth token -- distinct from the hardcoded
    GET /github/repositories mock below, which returns fixed sample data regardless of
    whether GitHub is even connected."""
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


@router.get("/github/repositories", status_code=status.HTTP_200_OK)
async def get_github_repositories(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve connected GitHub repositories for the organization."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_repositories": 3,
        "repositories": [
            {
                "id": 101,
                "name": "AI-Project-Manager",
                "full_name": "DinukaShavi/AI-Project-Manager",
                "private": False,
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager",
                "description": "Enterprise AI-Powered Technical Project Manager System",
                "default_branch": "main",
                "open_issues_count": 4,
                "stargazers_count": 128,
                "updated_at": "2026-07-25T12:00:00Z"
            },
            {
                "id": 102,
                "name": "ai-tpm-engine",
                "full_name": "DinukaShavi/ai-tpm-engine",
                "private": True,
                "html_url": "https://github.com/DinukaShavi/ai-tpm-engine",
                "description": "Multi-agent HTN planning & pgvector context retrieval engine",
                "default_branch": "main",
                "open_issues_count": 2,
                "stargazers_count": 45,
                "updated_at": "2026-07-24T18:30:00Z"
            },
            {
                "id": 103,
                "name": "ai-tpm-infra",
                "full_name": "DinukaShavi/ai-tpm-infra",
                "private": True,
                "html_url": "https://github.com/DinukaShavi/ai-tpm-infra",
                "description": "Terraform AWS RDS, ElastiCache & EKS deployment modules",
                "default_branch": "main",
                "open_issues_count": 0,
                "stargazers_count": 12,
                "updated_at": "2026-07-25T08:00:00Z"
            }
        ]
    }


@router.get("/github/pull-requests", status_code=status.HTTP_200_OK)
async def get_github_pull_requests(
    organization_id: Optional[UUID] = None,
    repository: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve pull requests across connected repositories."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_pull_requests": 4,
        "pull_requests": [
            {
                "id": 501,
                "number": 42,
                "title": "Implement Multi-Dimensional Rate Limiter & Token Bucket Engine",
                "state": "open",
                "author": "dinukashavi",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/pull/42",
                "created_at": "2026-07-25T06:30:00Z",
                "draft": False,
                "additions": 420,
                "deletions": 12,
                "labels": ["enhancement", "security"]
            },
            {
                "id": 502,
                "number": 41,
                "title": "Add OpenTelemetry Distributed Tracing & Prometheus Exporter",
                "state": "merged",
                "author": "dev-lead",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/pull/41",
                "created_at": "2026-07-24T14:20:00Z",
                "draft": False,
                "additions": 310,
                "deletions": 45,
                "labels": ["observability"]
            },
            {
                "id": 503,
                "number": 40,
                "title": "Configure Row-Level Security (RLS) Tenant Isolation Policies",
                "state": "merged",
                "author": "sec-team",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/pull/40",
                "created_at": "2026-07-23T11:00:00Z",
                "draft": False,
                "additions": 185,
                "deletions": 8,
                "labels": ["security", "database"]
            },
            {
                "id": 504,
                "number": 39,
                "title": "Next.js 15 Dark Glassmorphism Dashboard UI Polish",
                "state": "open",
                "author": "frontend-dev",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/pull/39",
                "created_at": "2026-07-25T09:15:00Z",
                "draft": False,
                "additions": 540,
                "deletions": 120,
                "labels": ["frontend", "ui/ux"]
            }
        ]
    }


@router.get("/github/commits", status_code=status.HTTP_200_OK)
async def get_github_commits(
    organization_id: Optional[UUID] = None,
    repository: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve recent commit activity log across repositories."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_commits": 5,
        "commits": [
            {
                "sha": "a1b2c3d4e5f67890123456789abcdef012345678",
                "short_sha": "a1b2c3d",
                "message": "feat: Add Centralized Frontend API Service Layer & Typed HTTP Client",
                "author": "Dinuka Shavi",
                "author_email": "dinuka@example.com",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "timestamp": "2026-07-25T13:58:00Z",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/commit/a1b2c3d"
            },
            {
                "sha": "b2c3d4e5f67890123456789abcdef012345679",
                "short_sha": "b2c3d4e",
                "message": "fix: Resolve Context Engine Search 422 Schema Validation Error",
                "author": "Dinuka Shavi",
                "author_email": "dinuka@example.com",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "timestamp": "2026-07-25T13:11:00Z",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/commit/b2c3d4e"
            },
            {
                "sha": "c3d4e5f67890123456789abcdef012345680",
                "short_sha": "c3d4e5f",
                "message": "feat: Implement Production Deployment Scaffolding (Terraform, k8s, CI/CD)",
                "author": "Dinuka Shavi",
                "author_email": "dinuka@example.com",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "timestamp": "2026-07-25T12:49:00Z",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/commit/c3d4e5f"
            },
            {
                "sha": "d4e5f67890123456789abcdef012345681",
                "short_sha": "d4e5f67",
                "message": "feat: Multi-Tenant Schema & Virtual Isolation Engine (Phase 15e)",
                "author": "Dinuka Shavi",
                "author_email": "dinuka@example.com",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "timestamp": "2026-07-24T17:30:00Z",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/commit/d4e5f67"
            },
            {
                "sha": "e5f67890123456789abcdef012345682",
                "short_sha": "e5f6789",
                "message": "feat: Knowledge Graph Relationship Weight Decay & Event Inference Pipeline",
                "author": "Dinuka Shavi",
                "author_email": "dinuka@example.com",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "timestamp": "2026-07-24T15:45:00Z",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/commit/e5f6789"
            }
        ]
    }


@router.get("/github/issues", status_code=status.HTTP_200_OK)
async def get_github_issues(
    organization_id: Optional[UUID] = None,
    repository: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve GitHub issue tracking tickets across repositories."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_issues": 4,
        "issues": [
            {
                "id": 901,
                "number": 105,
                "title": "Configure Slack & GitHub Webhook HMAC Verification",
                "state": "open",
                "author": "dinukashavi",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/issues/105",
                "created_at": "2026-07-25T08:00:00Z",
                "comments_count": 3,
                "labels": ["integration", "high-priority"]
            },
            {
                "id": 902,
                "number": 104,
                "title": "Next.js 15 Dark Glassmorphism Component Polish",
                "state": "open",
                "author": "frontend-dev",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/issues/104",
                "created_at": "2026-07-25T07:15:00Z",
                "comments_count": 1,
                "labels": ["ui/ux"]
            },
            {
                "id": 903,
                "number": 103,
                "title": "Optimize HNSW Vector Index Rebuild Sweeps",
                "state": "closed",
                "author": "database-lead",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/issues/103",
                "created_at": "2026-07-24T16:00:00Z",
                "comments_count": 5,
                "labels": ["performance", "pgvector"]
            },
            {
                "id": 904,
                "number": 102,
                "title": "Build Outbox Pattern Worker Event Bus Pipeline",
                "state": "closed",
                "author": "backend-dev",
                "repository": repository or "DinukaShavi/AI-Project-Manager",
                "html_url": "https://github.com/DinukaShavi/AI-Project-Manager/issues/102",
                "created_at": "2026-07-23T14:30:00Z",
                "comments_count": 2,
                "labels": ["backend", "events"]
            }
        ]
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
    organization_id: Optional[UUID] = None,
    project_key: Optional[str] = "TPM",
    db: AsyncSession = Depends(get_db)
):
    """Retrieve Jira issue backlog and sprint tickets."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_issues": 4,
        "issues": [
            {"id": "20001", "key": "TPM-101", "summary": "Implement pgvector SQLAlchemy Fallback", "status": "In Progress", "priority": "High", "assignee": "Dinuka Shavi", "story_points": 5},
            {"id": "20002", "key": "TPM-102", "summary": "Build Outbox Pattern Worker Event Bus", "status": "Done", "priority": "Highest", "assignee": "Dev Lead", "story_points": 8},
            {"id": "20003", "key": "TPM-103", "summary": "Create Multi-Agent DAG Workflow Engine", "status": "Done", "priority": "High", "assignee": "AI Architect", "story_points": 8},
            {"id": "20004", "key": "TPM-104", "summary": "Next.js 15 Dark Glassmorphism Integration", "status": "In Progress", "priority": "Medium", "assignee": "Frontend Lead", "story_points": 5}
        ]
    }


@router.get("/jira/sprints", status_code=status.HTTP_200_OK)
async def get_jira_sprints(
    organization_id: Optional[UUID] = None,
    project_key: Optional[str] = "TPM",
    db: AsyncSession = Depends(get_db)
):
    """Retrieve active and upcoming Jira sprints."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_sprints": 2,
        "sprints": [
            {"id": 301, "name": "Sprint 14 - Production Launch", "state": "active", "start_date": "2026-07-20T00:00:00Z", "end_date": "2026-08-03T00:00:00Z", "completed_story_points": 21, "total_story_points": 34},
            {"id": 302, "name": "Sprint 15 - Performance & Scaling", "state": "future", "start_date": "2026-08-04T00:00:00Z", "end_date": "2026-08-18T00:00:00Z", "completed_story_points": 0, "total_story_points": 40}
        ]
    }


@router.get("/jira/workload", status_code=status.HTTP_200_OK)
async def get_jira_workload(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve story points distribution across team members."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "team_workload": [
            {"assignee": "Dinuka Shavi", "assigned_issues": 5, "total_story_points": 18, "capacity_percentage": 90.0},
            {"assignee": "Dev Lead", "assigned_issues": 3, "total_story_points": 12, "capacity_percentage": 60.0},
            {"assignee": "Frontend Lead", "assigned_issues": 2, "total_story_points": 8, "capacity_percentage": 40.0}
        ]
    }


@router.get("/jira/velocity", status_code=status.HTTP_200_OK)
async def get_jira_velocity(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve historical sprint velocity metrics."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "average_velocity": 32.5,
        "sprint_velocity_history": [
            {"sprint": "Sprint 11", "committed": 30, "completed": 28},
            {"sprint": "Sprint 12", "committed": 35, "completed": 34},
            {"sprint": "Sprint 13", "committed": 36, "completed": 36},
            {"sprint": "Sprint 14", "committed": 34, "completed": 21}
        ]
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
    Slack API call via the stored OAuth token -- distinct from the hardcoded GET /slack/channels
    mock below, which returns fixed sample data regardless of whether Slack is even connected."""
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


@router.get("/slack/channels", status_code=status.HTTP_200_OK)
async def get_slack_channels(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve connected Slack workspace channels."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_channels": 4,
        "channels": [
            {"id": "C01ABCDEF01", "name": "proj-ai-tpm", "is_private": False, "members_count": 14, "topic": "AI-TPM Architecture & Sprint Standups"},
            {"id": "C01ABCDEF02", "name": "dev-engineering", "is_private": False, "members_count": 28, "topic": "General Engineering Discussions"},
            {"id": "C01ABCDEF03", "name": "alerts-production", "is_private": True, "members_count": 8, "topic": "Production System & Security Alerts"},
            {"id": "C01ABCDEF04", "name": "releases-changelog", "is_private": False, "members_count": 45, "topic": "Release Announcements"}
        ]
    }


@router.get("/slack/messages", status_code=status.HTTP_200_OK)
async def get_slack_messages(
    organization_id: Optional[UUID] = None,
    channel_id: Optional[str] = "C01ABCDEF01",
    db: AsyncSession = Depends(get_db)
):
    """Retrieve recent messages and bot notifications in a Slack channel."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "channel_id": channel_id,
        "total_messages": 4,
        "messages": [
            {"ts": "1721890000.000100", "user": "U0112233", "user_name": "Dinuka Shavi", "text": "Successfully merged PR #42 (Multi-Dimensional Rate Limiter & Token Bucket).", "timestamp": "2026-07-25T08:30:00Z"},
            {"ts": "1721886400.000200", "user": "USLACKBOT", "user_name": "AI-TPM Bot", "text": "🤖 AI Risk Alert: Delivery risk index is low (0.15). Sprint completion predicted on track.", "timestamp": "2026-07-25T07:30:00Z"},
            {"ts": "1721882800.000300", "user": "U0112244", "user_name": "Dev Lead", "text": "Master QA regression suite ran with 34/34 passing test suites.", "timestamp": "2026-07-25T06:30:00Z"},
            {"ts": "1721879200.000400", "user": "U0112255", "user_name": "Frontend Lead", "text": "Next.js 15 dark glassmorphism dashboard build succeeded.", "timestamp": "2026-07-25T05:30:00Z"}
        ]
    }


@router.get("/slack/users", status_code=status.HTTP_200_OK)
async def get_slack_users(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve active Slack workspace team members."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_users": 3,
        "users": [
            {"id": "U0112233", "name": "dinuka.shavi", "real_name": "Dinuka Shavi", "role": "Lead Architect", "is_bot": False, "status_text": "Coding AI-TPM Backend"},
            {"id": "U0112244", "name": "dev.lead", "real_name": "Dev Lead", "role": "Senior Engineer", "is_bot": False, "status_text": "Reviewing PRs"},
            {"id": "U0112255", "name": "frontend.lead", "real_name": "Frontend Lead", "role": "UI Architect", "is_bot": False, "status_text": "Building Next.js 15 UI"}
        ]
    }


@router.get("/slack/activity", status_code=status.HTTP_200_OK)
async def get_slack_activity_analysis(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve team activity & discussion sentiment analytics."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "daily_message_volume": 142,
        "sentiment_score": 0.88,
        "top_discussed_topics": ["pgvector migration", "OpenTelemetry tracing", "Multi-tenant RLS"],
        "activity_by_hour": [
            {"hour": "08:00", "messages": 12},
            {"hour": "10:00", "messages": 45},
            {"hour": "12:00", "messages": 28},
            {"hour": "14:00", "messages": 35},
            {"hour": "16:00", "messages": 22}
        ]
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
    }


@router.get("/calendar/meetings", status_code=status.HTTP_200_OK)
async def list_calendar_meetings(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List Synced Calendar Meetings for a project (database_schema_design.md section 19,
    ui_ux_design.md section 10 Calendar page). Reads the real Meeting rows written by
    POST /calendar/sync -- distinct from the hardcoded, unauthenticated GET /google/meetings
    mock below, which returns fixed sample data regardless of tenant or actual sync state."""
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
            }
            for m in meetings
        ],
    }


@router.get("/google/events", status_code=status.HTTP_200_OK)
async def get_google_events(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve team calendar events and sprint milestone sync."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_events": 4,
        "events": [
            {"id": "evt-101", "summary": "Sprint 14 Planning & Standup", "start_time": "2026-07-26T09:00:00Z", "end_time": "2026-07-26T09:30:00Z", "organizer": "dinuka@example.com", "location": "Google Meet", "attendees_count": 5},
            {"id": "evt-102", "summary": "Architecture Review: OpenTelemetry & RLS", "start_time": "2026-07-26T14:00:00Z", "end_time": "2026-07-26T15:00:00Z", "organizer": "architect@example.com", "location": "Google Meet", "attendees_count": 4},
            {"id": "evt-103", "summary": "Mid-Sprint Retrospective", "start_time": "2026-07-28T16:00:00Z", "end_time": "2026-07-28T17:00:00Z", "organizer": "pm@example.com", "location": "Google Meet", "attendees_count": 6},
            {"id": "evt-104", "summary": "Production Blue/Green Deployment Window", "start_time": "2026-08-01T10:00:00Z", "end_time": "2026-08-01T11:30:00Z", "organizer": "devops@example.com", "location": "War Room", "attendees_count": 3}
        ]
    }


@router.get("/google/meetings", status_code=status.HTTP_200_OK)
async def get_google_meetings(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve scheduled Google Meet links and agenda items."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "meetings": [
            {"meeting_id": "meet-a1b2", "title": "Daily Sprint Standup", "join_url": "https://meet.google.com/abc-defg-hij", "start_time": "2026-07-26T09:00:00Z", "status": "scheduled"},
            {"meeting_id": "meet-c3d4", "title": "Architecture Deep Dive", "join_url": "https://meet.google.com/klm-nopq-rst", "start_time": "2026-07-26T14:00:00Z", "status": "scheduled"}
        ]
    }


@router.get("/google/availability", status_code=status.HTTP_200_OK)
async def get_google_availability(
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve team availability matrix for automated meeting scheduling."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "available_slots": [
            {"date": "2026-07-26", "slot": "11:00 AM - 12:00 PM UTC", "participants_available": ["Dinuka Shavi", "Dev Lead", "Frontend Lead"]},
            {"date": "2026-07-26", "slot": "03:00 PM - 04:00 PM UTC", "participants_available": ["Dinuka Shavi", "Dev Lead"]},
            {"date": "2026-07-27", "slot": "10:00 AM - 11:00 AM UTC", "participants_available": ["Dinuka Shavi", "Frontend Lead"]}
        ]
    }



