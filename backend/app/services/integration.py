from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.integrations.base import BaseConnector
from app.integrations.github import GitHubConnector
from app.integrations.jira import JiraConnector
from app.integrations.slack import SlackConnector
from app.integrations.calendar import GoogleCalendarConnector
from app.models.event import Event

class IntegrationService:
    def __init__(self, session: AsyncSession):
        """Integration Service orchestrating provider connectors and webhook outbox ingestion."""
        self.session = session

    def get_connector(self, provider: str, credentials: Optional[Dict[str, Any]] = None) -> BaseConnector:
        """Connector factory instantiating platform adapters."""
        creds = credentials or {}
        p = provider.lower()
        if p == "github":
            return GitHubConnector(token=creds.get("token"))
        elif p == "jira":
            return JiraConnector(
                domain=creds.get("domain"),
                api_token=creds.get("api_token"),
                user_email=creds.get("user_email")
            )
        elif p == "slack":
            return SlackConnector(bot_token=creds.get("bot_token"))
        elif p in ["google", "google_calendar", "calendar"]:
            return GoogleCalendarConnector(access_token=creds.get("access_token"))
        else:
            raise ValueError(f"Unsupported integration provider: {provider}")

    async def receive_webhook(
        self,
        provider: str,
        payload_bytes: bytes,
        payload_json: Dict[str, Any],
        headers: Dict[str, str],
        organization_id: UUID,
        project_id: Optional[UUID] = None,
        secret: Optional[str] = None
    ) -> Event:
        """Verify, normalize, and ingest external webhook payloads as outbox Event entries."""
        connector = self.get_connector(provider)
        
        # Determine signature header key based on provider
        sig_header_keys = {
            "github": "x-hub-signature-256",
            "jira": "x-jira-signature",
            "slack": "x-slack-signature",
            "google_calendar": "x-goog-channel-token"
        }
        sig_key = sig_header_keys.get(provider.lower(), "x-signature")
        signature = headers.get(sig_key, headers.get("signature", ""))

        # Verify signature if secret is configured
        if secret:
            is_valid = connector.verify_webhook_signature(payload_bytes, signature, secret)
            if not is_valid:
                raise ValueError(f"Invalid webhook signature for provider '{provider}'.")

        # Normalize payload into standard event packet
        normalized = connector.parse_webhook_event(payload_json, headers)
        
        # Save to database Event outbox table atomically
        db_event = Event(
            organization_id=organization_id,
            project_id=project_id,
            routing_key=normalized["routing_key"],
            payload=normalized,
            processed=False
        )
        self.session.add(db_event)
        await self.session.commit()
        await self.session.refresh(db_event)
        
        return db_event
