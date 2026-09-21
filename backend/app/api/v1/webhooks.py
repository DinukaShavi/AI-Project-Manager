import json
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.api.deps import get_db
from app.core.config import settings
from app.services.integration import IntegrationService

router = APIRouter()

_KNOWN_PROVIDERS = {"github", "jira", "slack", "google_calendar"}

_PROVIDER_SECRETS = {
    "github": lambda: settings.GITHUB_WEBHOOK_SECRET,
    "jira": lambda: settings.JIRA_WEBHOOK_SECRET,
    "slack": lambda: settings.SLACK_SIGNING_SECRET,
    # Google Calendar push notifications carry no per-message body signature -- the channel
    # token itself (verified inside receive_webhook via the connector) was previously sourced
    # from GOOGLE_CLIENT_SECRET, a real OAuth credential unrelated to this channel; that
    # conflation is removed rather than replaced, since the per-org webhook_token URL is
    # already this provider's real authentication now.
    "google_calendar": lambda: None,
}


@router.post("/{provider}/{webhook_token}", status_code=status.HTTP_202_ACCEPTED)
async def receive_provider_webhook(
    provider: str,
    webhook_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Real per-organization webhook intake. The URL path itself (an unguessable token
    generated when the org connected this provider) identifies and authenticates the owning
    organization -- organization_id is never accepted from the request. Provider signature
    verification (when a secret is configured server-side) is a second, independent layer on
    top of that, not the only one."""
    provider_key = provider.lower()
    if provider_key not in _KNOWN_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown webhook provider.")

    service = IntegrationService(db)
    organization_id = await service.resolve_organization_for_webhook_token(provider_key, webhook_token)
    if organization_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")

    raw_body = await request.body()
    try:
        json_body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        json_body = {}

    if provider_key == "slack" and json_body.get("type") == "url_verification":
        return Response(content=json_body.get("challenge", ""), media_type="text/plain")

    headers = {k.lower(): v for k, v in request.headers.items()}
    webhook_secret = _PROVIDER_SECRETS[provider_key]()

    try:
        event = await service.receive_webhook(
            provider=provider_key,
            payload_bytes=raw_body,
            payload_json=json_body,
            headers=headers,
            organization_id=organization_id,
            secret=webhook_secret,
        )
        return {"status": "accepted", "event_id": str(event.id), "routing_key": event.routing_key}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
