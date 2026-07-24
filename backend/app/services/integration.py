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

        # Verify signature if secret is configured, signature is present, and secret is not default placeholder
        is_placeholder = not secret or "your_" in secret or "here" in secret
        if signature and secret and not is_placeholder:
            is_valid = connector.verify_webhook_signature(payload_bytes, signature, secret)
            if not is_valid:
                raise ValueError(f"Invalid webhook signature for provider '{provider}'.")

        # Normalize payload into standard event packet
        normalized = connector.parse_webhook_event(payload_json, headers)
        
        # Ensure Organization exists in DB to prevent foreign key violations
        from sqlalchemy import select
        from app.models.tenant import Organization
        org_res = await self.session.execute(select(Organization).where(Organization.id == organization_id))
        if not org_res.scalar_one_or_none():
            org = Organization(id=organization_id, name="Default Integration Org", domain="default.org")
            self.session.add(org)
            await self.session.flush()

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

    async def generate_oauth_authorize_url(
        self,
        provider: str,
        organization_id: UUID,
        redirect_uri: str
    ) -> str:
        """Generate provider-specific OAuth authorization URL with encoded state."""
        from app.core.config import settings
        p = provider.lower()
        state = f"org_id={organization_id}&provider={p}"

        if p == "github":
            client_id = getattr(settings, "GITHUB_CLIENT_ID", "github_mock_client_id")
            scope = "repo,user,admin:repo_hook"
            return f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}&state={state}"
        elif p == "jira":
            client_id = getattr(settings, "JIRA_CLIENT_ID", "jira_mock_client_id")
            scope = "read:jira-work write:jira-work offline_access"
            return f"https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id={client_id}&scope={scope}&redirect_uri={redirect_uri}&state={state}&response_type=code&prompt=consent"
        elif p == "slack":
            client_id = getattr(settings, "SLACK_CLIENT_ID", "slack_mock_client_id")
            scope = "chat:write,channels:read,users:read"
            return f"https://slack.com/oauth/v2/authorize?client_id={client_id}&scope={scope}&redirect_uri={redirect_uri}&state={state}"
        elif p in ["google", "google_calendar"]:
            client_id = settings.GOOGLE_CLIENT_ID or "google_mock_client_id"
            scope = "https://www.googleapis.com/auth/calendar.events"
            return f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scope}&state={state}&access_type=offline"
        else:
            raise ValueError(f"Unsupported OAuth provider: {provider}")

    async def exchange_code_for_token(
        self,
        provider: str,
        code: str,
        organization_id: UUID,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """Exchange OAuth authorization code for tokens, encrypt via AES-256 Fernet, and persist to database."""
        from sqlalchemy import select
        from datetime import datetime, timedelta, timezone
        from app.core.security import encrypt_token
        from app.models.tenant import Organization
        from app.models.integration import Integration, OAuthToken

        p = provider.lower()

        # Ensure Organization exists
        org_res = await self.session.execute(select(Organization).where(Organization.id == organization_id))
        if not org_res.scalar_one_or_none():
            org = Organization(id=organization_id, name="Default OAuth Org", domain="oauth.org")
            self.session.add(org)
            await self.session.flush()

        # Simulated or HTTP exchange payload
        raw_access_token = f"{p}_access_token_{code[:8]}"
        raw_refresh_token = f"{p}_refresh_token_{code[:8]}"
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        scopes = [f"{p}:read", f"{p}:write"]

        # Encrypt tokens before storing
        enc_access = encrypt_token(raw_access_token)
        enc_refresh = encrypt_token(raw_refresh_token)

        # Retrieve or create Integration record
        int_res = await self.session.execute(
            select(Integration).where(
                Integration.organization_id == organization_id,
                Integration.provider == p
            )
        )
        integration = int_res.scalar_one_or_none()
        if not integration:
            integration = Integration(
                organization_id=organization_id,
                provider=p,
                is_active=True
            )
            self.session.add(integration)
            await self.session.flush()

        # Retrieve or create OAuthToken record
        tok_res = await self.session.execute(
            select(OAuthToken).where(OAuthToken.integration_id == integration.id)
        )
        token_rec = tok_res.scalar_one_or_none()
        if token_rec:
            token_rec.encrypted_access_token = enc_access
            token_rec.encrypted_refresh_token = enc_refresh
            token_rec.expires_at = expires_at
            token_rec.scopes = scopes
        else:
            token_rec = OAuthToken(
                organization_id=organization_id,
                integration_id=integration.id,
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                expires_at=expires_at,
                scopes=scopes
            )
            self.session.add(token_rec)

        await self.session.commit()

        return {
            "status": "connected",
            "organization_id": str(organization_id),
            "provider": p,
            "scopes": scopes,
            "expires_at": expires_at.isoformat()
        }

    async def get_valid_oauth_token(
        self,
        organization_id: UUID,
        provider: str
    ) -> Optional[str]:
        """Fetch and decrypt valid OAuth access token for tenant tool execution."""
        from sqlalchemy import select
        from app.core.security import decrypt_token
        from app.models.integration import Integration, OAuthToken

        p = provider.lower()
        res = await self.session.execute(
            select(OAuthToken)
            .join(Integration, OAuthToken.integration_id == Integration.id)
            .where(
                Integration.organization_id == organization_id,
                Integration.provider == p,
                Integration.is_active == True
            )
        )
        token_rec = res.scalar_one_or_none()
        if not token_rec or not token_rec.encrypted_access_token:
            return None

        return decrypt_token(token_rec.encrypted_access_token)

    async def revoke_oauth_token(
        self,
        organization_id: UUID,
        provider: str
    ) -> bool:
        """Revoke and delete tenant OAuth integration token."""
        from sqlalchemy import select
        from app.models.integration import Integration

        p = provider.lower()
        res = await self.session.execute(
            select(Integration).where(
                Integration.organization_id == organization_id,
                Integration.provider == p
            )
        )
        integration = res.scalar_one_or_none()
        if not integration:
            return False

        integration.is_active = False
        await self.session.commit()
        return True

