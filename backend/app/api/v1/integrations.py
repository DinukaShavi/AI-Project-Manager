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
