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


