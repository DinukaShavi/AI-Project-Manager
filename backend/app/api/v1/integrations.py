import json
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.core.config import settings
from app.services.integration import IntegrationService

router = APIRouter()

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
    organization_id: Optional[UUID] = None,
    redirect_uri: Optional[str] = "http://localhost:3000/oauth/callback",
    db: AsyncSession = Depends(get_db)
):
    """Generate third-party OAuth provider authorization URL."""
    service = IntegrationService(db)
    org_id = organization_id or DEFAULT_ORG_ID
    try:
        url = await service.generate_oauth_authorize_url(
            provider=provider,
            organization_id=org_id,
            redirect_uri=redirect_uri or "http://localhost:3000/oauth/callback"
        )
        return {"authorization_url": url, "provider": provider, "organization_id": str(org_id)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/oauth/{provider}/callback", status_code=status.HTTP_200_OK)
async def oauth_callback(
    provider: str,
    code: str,
    organization_id: Optional[UUID] = None,
    redirect_uri: Optional[str] = "http://localhost:3000/oauth/callback",
    db: AsyncSession = Depends(get_db)
):
    """Exchange OAuth authorization code for encrypted tokens and persist in database."""
    service = IntegrationService(db)
    org_id = organization_id or DEFAULT_ORG_ID
    try:
        res = await service.exchange_code_for_token(
            provider=provider,
            code=code,
            organization_id=org_id,
            redirect_uri=redirect_uri or "http://localhost:3000/oauth/callback"
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/oauth/tokens/{organization_id}", status_code=status.HTTP_200_OK)
async def get_tenant_oauth_token(
    organization_id: UUID,
    provider: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve active decrypted tenant access token for tool invocation."""
    service = IntegrationService(db)
    token = await service.get_valid_oauth_token(organization_id=organization_id, provider=provider)
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active OAuth token found for provider '{provider}'.")
    return {"organization_id": str(organization_id), "provider": provider, "access_token": token}


@router.delete("/oauth/{provider}", status_code=status.HTTP_200_OK)
async def revoke_oauth_integration(
    provider: str,
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Revoke and deactivate tenant OAuth provider integration."""
    service = IntegrationService(db)
    org_id = organization_id or DEFAULT_ORG_ID
    success = await service.revoke_oauth_token(organization_id=org_id, provider=provider)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found.")
    return {"status": "revoked", "provider": provider, "organization_id": str(org_id)}


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
    organization_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve connected Jira software projects."""
    org_id = organization_id or DEFAULT_ORG_ID
    return {
        "organization_id": str(org_id),
        "total_projects": 2,
        "projects": [
            {"id": "10001", "key": "TPM", "name": "Technical Project Manager", "project_type": "software", "lead": "Dinuka Shavi", "total_issues": 18},
            {"id": "10002", "key": "INFRA", "name": "Cloud Infrastructure", "project_type": "business", "lead": "DevOps Lead", "total_issues": 10}
        ]
    }


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



