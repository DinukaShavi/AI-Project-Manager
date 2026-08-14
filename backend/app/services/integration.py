from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.integrations.base import BaseConnector
from app.integrations.github import GitHubConnector
from app.integrations.jira import JiraConnector
from app.integrations.slack import SlackConnector
from app.integrations.calendar import GoogleCalendarConnector
from app.models.event import Event
from app.models.project import Project, Repository, SlackChannelMapping, Meeting
from app.services.audit import AuditService

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

        # For Slack, auto-resolve project_id from the channel-to-project mapping when the
        # caller didn't explicitly pass one, so messages route to the correct project context.
        if project_id is None and provider.lower() == "slack" and normalized.get("channel"):
            project_id = await self.resolve_project_for_slack_channel(organization_id, normalized["channel"])

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
            client_id = settings.GITHUB_CLIENT_ID or "github_mock_client_id"
            scope = "repo,user,admin:repo_hook"
            return f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}&state={state}"
        elif p == "jira":
            client_id = settings.JIRA_CLIENT_ID or "jira_mock_client_id"
            scope = "read:jira-work write:jira-work offline_access"
            return f"https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id={client_id}&scope={scope}&redirect_uri={redirect_uri}&state={state}&response_type=code&prompt=consent"
        elif p == "slack":
            client_id = settings.SLACK_CLIENT_ID or "slack_mock_client_id"
            scope = "chat:write,channels:read,users:read"
            return f"https://slack.com/oauth/v2/authorize?client_id={client_id}&scope={scope}&redirect_uri={redirect_uri}&state={state}"
        elif p in ["google", "google_calendar"]:
            client_id = settings.GOOGLE_CLIENT_ID or "google_mock_client_id"
            scope = "https://www.googleapis.com/auth/calendar.events"
            return f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scope}&state={state}&access_type=offline"
        else:
            raise ValueError(f"Unsupported OAuth provider: {provider}")

    def _get_provider_client_credentials(self, provider: str) -> "Tuple[str, str]":
        """Shared client_id/client_secret lookup used by both authorization-code exchange
        and token refresh -- every provider's OAuth app is configured once, the same
        credentials apply to both grant types. Raises ValueError if the provider is
        unsupported or its credentials aren't configured."""
        from app.core.config import settings

        creds = {
            "github": (settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET),
            "jira": (settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET),
            "slack": (settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET),
            "google": (settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET),
            "google_calendar": (settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET),
        }
        if provider not in creds:
            raise ValueError(f"Unsupported OAuth provider: {provider}")
        client_id, client_secret = creds[provider]
        if not client_id or not client_secret:
            raise ValueError(
                f"OAuth client credentials for '{provider}' are not configured "
                f"(set {provider.upper()}_CLIENT_ID / {provider.upper()}_CLIENT_SECRET)."
            )
        return client_id, client_secret

    async def _exchange_code_with_provider(
        self,
        provider: str,
        code: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """Make the real HTTP call to a provider's OAuth token endpoint and return its
        parsed JSON response. Raises ValueError on missing credentials or a provider error."""
        import httpx

        client_id, client_secret = self._get_provider_client_credentials(provider)

        async with httpx.AsyncClient(timeout=15.0) as client:
            if provider == "github":
                resp = await client.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={"client_id": client_id, "client_secret": client_secret, "code": code, "redirect_uri": redirect_uri},
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise ValueError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")
                return data

            elif provider == "jira":
                resp = await client.post(
                    "https://auth.atlassian.com/oauth/token",
                    json={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                )
                if resp.status_code >= 400:
                    raise ValueError(f"Jira OAuth error ({resp.status_code}): {resp.text}")
                return resp.json()

            elif provider == "slack":
                resp = await client.post(
                    "https://slack.com/api/oauth.v2.access",
                    data={"client_id": client_id, "client_secret": client_secret, "code": code, "redirect_uri": redirect_uri},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise ValueError(f"Slack OAuth error: {data.get('error', 'unknown_error')}")
                return data

            else:  # google / google_calendar
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                if resp.status_code >= 400:
                    raise ValueError(f"Google OAuth error ({resp.status_code}): {resp.text}")
                return resp.json()

    async def _refresh_token_with_provider(self, provider: str, refresh_token: str) -> Dict[str, Any]:
        """Make the real HTTP call to a provider's OAuth token endpoint using the
        refresh_token grant -- the exact same token endpoints _exchange_code_with_provider
        already uses, just a different grant_type/params, per each provider's standard
        OAuth 2.0 refresh behavior:

        - Google: grant_type=refresh_token at https://oauth2.googleapis.com/token. Google
          does not normally reissue a new refresh_token on refresh (the original stays
          valid), but a replacement is honored if one is returned.
        - GitHub: grant_type=refresh_token at https://github.com/login/oauth/access_token.
          Only applicable to a GitHub App configured with expiring user tokens -- classic
          GitHub OAuth Apps issue non-expiring tokens with no refresh_token at all, so no
          such integration in this system would ever reach this call (get_valid_oauth_token
          raises before this point when encrypted_refresh_token is empty).
        - Jira (Atlassian 3LO): grant_type=refresh_token at
          https://auth.atlassian.com/oauth/token. Atlassian rotates the refresh_token on
          every use, matching generate_oauth_authorize_url's existing "offline_access" scope
          request for Jira.
        - Slack is intentionally NOT implemented here: this codebase's Slack OAuth exchange
          (oauth.v2.access) does not implement Slack's opt-in token-rotation feature, so no
          Slack integration created through this codebase ever has a refresh_token stored --
          get_valid_oauth_token's "no refresh token available" check raises before a Slack
          call could ever reach this method.

        Raises ValueError if the provider explicitly rejects the refresh (invalid/revoked
        refresh token, bad client credentials) -- an auth-level failure requiring
        re-authorization. Network/transport failures (httpx exceptions) propagate
        unwrapped, distinguishing a transient provider outage from an auth failure.
        """
        import httpx

        client_id, client_secret = self._get_provider_client_credentials(provider)

        async with httpx.AsyncClient(timeout=15.0) as client:
            if provider == "github":
                resp = await client.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={"client_id": client_id, "client_secret": client_secret, "grant_type": "refresh_token", "refresh_token": refresh_token},
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise ValueError(f"GitHub OAuth refresh error: {data.get('error_description', data['error'])}")
                return data

            elif provider == "jira":
                resp = await client.post(
                    "https://auth.atlassian.com/oauth/token",
                    json={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                    },
                )
                if resp.status_code >= 400:
                    raise ValueError(f"Jira OAuth refresh error ({resp.status_code}): {resp.text}")
                return resp.json()

            elif provider in ("google", "google_calendar"):
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                if resp.status_code >= 400:
                    raise ValueError(f"Google OAuth refresh error ({resp.status_code}): {resp.text}")
                return resp.json()

            else:
                raise ValueError(f"Provider '{provider}' does not support OAuth token refresh under the currently configured integration model.")

    async def _broadcast_integration_status(self, organization_id: UUID, provider: str, connection_status: str) -> None:
        """Broadcast an integration connection-status change over the org-scoped
        WebSocket channel (implementation_roadmap.md Milestone 6: "WebSocket Events:
        Broadcast status updates when integrations are connected"; "connection dashboard
        updates in real-time"). Reuses the existing ConnectionManager -- the only
        real-time broadcast mechanism in this codebase -- rather than a second event
        system. Payload never includes token/credential material, matching
        api_contract.md section 3's documented "channel_update" envelope shape."""
        from datetime import datetime, timezone
        from app.realtime.connection_manager import get_connection_manager

        await get_connection_manager().broadcast_to_organization(
            {
                "event": "integration_status_update",
                "payload": {
                    "provider": provider,
                    "status": connection_status,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            organization_id,
        )

    def _extract_identity_from_token_response(self, provider: str, token_data: Dict[str, Any]) -> Optional[Dict[str, Optional[str]]]:
        """Pull the provider's own stable account/workspace identity out of data ALREADY
        present in the OAuth token-exchange response, when doing so requires no additional
        API call and no additional OAuth scope beyond what this deployment already requests.

        Returns None (never a fabricated identity) when the current response/scope doesn't
        carry it -- Jira (needs Atlassian's accessible-resources + /me) and Google (needs an
        `openid` scope this deployment doesn't currently request plus a userinfo call) are
        deliberately left for a follow-up phase. GitHub's identity is resolved separately, via
        _fetch_identity_via_api, since its token response carries no identity at all and
        needs one additional real API call rather than free data already in this response.

        Slack's oauth.v2.access response uniquely already includes both pieces for free:
        `authed_user.id` (the stable Slack user id of whoever completed the install) and
        `team.id`/`team.name` (the connected workspace) -- see api.slack.com/methods/oauth.v2.access.
        """
        if provider == "slack":
            authed_user = token_data.get("authed_user") or {}
            team = token_data.get("team") or {}
            external_account_id = authed_user.get("id")
            if not external_account_id:
                return None
            return {
                "external_account_id": external_account_id,
                "external_display_name": None,  # not present in this response; a future
                                                  # users.info call could populate it later
                "workspace_id": team.get("id"),
                "workspace_name": team.get("name"),
            }
        return None

    async def _fetch_identity_via_api(self, provider: str, access_token: str) -> Optional[Dict[str, Optional[str]]]:
        """For providers whose identity isn't present in the token-exchange response itself
        (see _extract_identity_from_token_response), make ONE additional real API call using
        the freshly obtained access token. Returns None (never fabricated) if the provider
        isn't supported yet or the call fails -- a failed identity lookup must never block the
        OAuth connection itself.

        GitHub has no single "workspace" the way Slack has exactly one team per install --
        a token can span a personal account plus multiple organizations simultaneously, so
        workspace_id/workspace_name are correctly left None here rather than guessing at one;
        each linked Repository row (external_repo_id) is the real per-resource granularity
        GitHub's own model supports, not a single org-level identifier.
        """
        if provider == "github":
            from app.integrations.github import GitHubConnector
            connector = GitHubConnector(token=access_token)
            try:
                user = await connector.get_authenticated_user()
            except Exception:
                return None
            external_account_id = user.get("id")
            if not external_account_id:
                return None
            return {
                "external_account_id": str(external_account_id),
                "external_display_name": user.get("login"),
                "workspace_id": None,
                "workspace_name": None,
            }
        if provider == "jira":
            # Atlassian 3LO identity/site resolution -- these are Atlassian-account-level
            # calls (api.atlassian.com), architecturally distinct from JiraConnector's
            # domain-scoped REST client (which still authenticates via a deployment-wide
            # Basic Auth email+API-token pair, unchanged by this method). Migrating
            # JiraConnector's actual issue/project data calls onto per-organization OAuth
            # bearer tokens (api.atlassian.com/ex/jira/{cloudId}/...) is deliberately left for
            # a follow-up phase; this method only resolves and records WHO connected and
            # WHICH real Jira site they granted access to.
            import httpx
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    me_res = await client.get(
                        "https://api.atlassian.com/me",
                        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                    )
                    me_res.raise_for_status()
                    me = me_res.json()

                    resources_res = await client.get(
                        "https://api.atlassian.com/oauth/token/accessible-resources",
                        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                    )
                    resources_res.raise_for_status()
                    resources = resources_res.json()
            except Exception:
                return None

            external_account_id = me.get("account_id")
            if not external_account_id:
                return None

            # A single Atlassian OAuth grant can list multiple accessible sites if the user
            # belongs to more than one Jira Cloud instance; consistent with Slack's one-
            # workspace-per-Integration assumption elsewhere in this codebase, the first
            # (Atlassian's own primary-first ordering) is treated as THE connected site.
            site = resources[0] if resources else {}
            return {
                "external_account_id": external_account_id,
                "external_display_name": me.get("name") or me.get("email"),
                "workspace_id": site.get("id"),
                "workspace_name": site.get("name") or site.get("url"),
            }
        return None

    async def exchange_code_for_token(
        self,
        provider: str,
        code: str,
        organization_id: UUID,
        redirect_uri: str,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Exchange OAuth authorization code for real provider tokens, encrypt via AES-256
        Fernet, and persist to database."""
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

        token_data = await self._exchange_code_with_provider(p, code, redirect_uri)

        raw_access_token = token_data.get("access_token")
        if not raw_access_token:
            raise ValueError(f"Provider '{p}' did not return an access_token: {token_data}")
        raw_refresh_token = token_data.get("refresh_token")

        expires_in = token_data.get("expires_in")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            if expires_in else datetime.now(timezone.utc) + timedelta(days=30)
        )

        raw_scope = token_data.get("scope", "")
        if isinstance(raw_scope, str):
            scopes = raw_scope.replace(",", " ").split() if raw_scope else []
        else:
            scopes = list(raw_scope) if raw_scope else []

        # Resolve the connecting user's real provider identity -- first from data already in
        # the token response (free, no extra call), falling back to one additional real API
        # call for providers that need it (currently GitHub only). Never fabricated; None if
        # neither path yields a real identity.
        identity_data = self._extract_identity_from_token_response(p, token_data)
        if not identity_data:
            identity_data = await self._fetch_identity_via_api(p, raw_access_token)

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

        # Capture the provider's own workspace identity resolved above -- never guessed,
        # never fabricated. Real for Slack (from the token response) today; None for GitHub
        # (no single workspace concept, see _fetch_identity_via_api) and still a no-op for
        # Jira/Google until their identity resolution ships.
        if identity_data:
            if identity_data.get("workspace_id"):
                integration.external_workspace_id = identity_data["workspace_id"]
            if identity_data.get("workspace_name"):
                integration.external_workspace_name = identity_data["workspace_name"]

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

        # Audited within the same unit of work as the token persistence itself (matching
        # workflow.py's execute_workflow convention) -- the OAuth grant is a security-
        # relevant action and must never be logged without the tokens actually having been
        # stored, or vice versa. Never includes access_token/refresh_token/client_secret/
        # authorization_code -- only the provider and granted scopes.
        await AuditService(self.session).log(
            organization_id=organization_id,
            user_id=user_id,
            action="oauth:connect",
            details={"provider": p, "scopes": scopes}
        )

        # Auto-link the connecting user's own external identity when the provider made it
        # trustworthily available above. This is a secondary enrichment on top of the org-
        # level integration connection, not a precondition for it -- if this same external
        # account already belongs to a different AI-TPM user in this organization, the
        # integration connection itself must still succeed; only the identity link is skipped.
        if identity_data and user_id:
            from app.services.external_identity import ExternalIdentityService
            try:
                await ExternalIdentityService(self.session).link_identity(
                    organization_id=organization_id,
                    user_id=user_id,
                    integration_id=integration.id,
                    provider=p,
                    external_account_id=identity_data["external_account_id"],
                    external_display_name=identity_data.get("external_display_name"),
                    verified_via_oauth=True,
                )
            except ValueError:
                pass

        await self.session.commit()
        await self._broadcast_integration_status(organization_id, p, "connected")

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
        """Central OAuth token-resolution path for every consumer (Calendar sync/poller,
        GitHub/Slack tools, and any future OAuth-based caller) -- the documented "OAuth
        Proxy" (detailed_component_architecture.md: "The framework handles token
        retrieval, decryption, validity checks, and renewal"). Callers should always ask
        here for a credential rather than reading OAuthToken directly or managing
        expiry/refresh themselves.

        Returns None if there's no active integration/token for this org+provider at all
        (nothing to refresh -- the org was simply never connected). If the stored access
        token is still valid, returns it directly. If it has expired, attempts a provider
        refresh and returns the new access token -- never silently returns a stale token.

        Raises PermissionError if refresh is impossible or fails (no refresh token stored,
        the provider rejects it as invalid/revoked, or OAuth client credentials aren't
        configured). Transient network/provider failures during refresh propagate
        unwrapped so callers can distinguish "needs re-authorization" from "temporary
        outage, try again later".
        """
        from sqlalchemy import select
        from datetime import datetime, timezone
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

        if not token_rec.expires_at or token_rec.expires_at > datetime.now(timezone.utc):
            return decrypt_token(token_rec.encrypted_access_token)

        try:
            return await self._refresh_oauth_token(organization_id, p, token_rec.id)
        except PermissionError as e:
            # Audited before the broadcast -- a reauth-required failure is a security-
            # relevant event (the connection can no longer act on this tenant's behalf
            # without a human re-authorizing it) and must leave a trail even though it's a
            # failure, not a successful mutation. str(e) here is always one of
            # _refresh_oauth_token's own generic PermissionError messages (never the raw
            # provider response body a wrapped ValueError might have carried, since that
            # text is deliberately not re-embedded when it's re-raised as PermissionError).
            await AuditService(self.session).log(
                organization_id=organization_id,
                action="oauth:reauth_required",
                details={"provider": p, "reason": str(e)}
            )
            await self.session.commit()
            # Surface the failure on the live connection-status dashboard
            # (implementation_roadmap.md Milestone 6) the moment it's discovered, rather
            # than only when the user next happens to look.
            await self._broadcast_integration_status(organization_id, p, "reauth_required")
            raise

    async def _refresh_oauth_token(self, organization_id: UUID, provider: str, token_rec_id: UUID) -> str:
        """Refresh an expired OAuth access token, distributed-lock-protected per
        (organization, provider) so two concurrent callers (e.g. two Calendar poller
        instances, or a poller racing a manual /calendar/sync request) can't both rotate
        the same refresh token at once -- GitHub and Jira both invalidate the previous
        refresh token the moment a new one is issued, so a lost race would otherwise
        strand the connection needing re-authorization. Reuses DistributedLockManager
        (the same Redlock manager used by the Calendar poller) rather than a second
        locking mechanism.
        """
        from datetime import datetime, timedelta, timezone
        from app.core.security import decrypt_token, encrypt_token
        from app.core.distributed_lock import get_lock_manager
        from app.models.integration import OAuthToken

        lock_manager = get_lock_manager()
        lock_key = f"oauth_refresh:{organization_id}:{provider}"
        try:
            async with lock_manager.lock(lock_key, ttl_seconds=30, max_wait_seconds=10.0, auto_renew=False):
                # Re-read after acquiring the lock -- another caller may have refreshed
                # (or the whole integration may have been revoked/deleted) while we waited.
                token_rec = await self.session.get(OAuthToken, token_rec_id)
                if not token_rec:
                    raise PermissionError(f"OAuth connection for provider '{provider}' no longer exists; re-authorization required.")
                if token_rec.expires_at and token_rec.expires_at <= datetime.now(timezone.utc):
                    raw_refresh = decrypt_token(token_rec.encrypted_refresh_token) if token_rec.encrypted_refresh_token else ""
                    if not raw_refresh:
                        raise PermissionError(f"No refresh token available for provider '{provider}'; the connection must be re-authorized.")

                    try:
                        token_data = await self._refresh_token_with_provider(provider, raw_refresh)
                    except ValueError as e:
                        raise PermissionError(f"OAuth refresh rejected for provider '{provider}': the connection must be re-authorized.") from e

                    new_access = token_data.get("access_token")
                    if not new_access:
                        raise PermissionError(f"Provider '{provider}' refresh response did not include a new access_token; re-authorization required.")

                    new_refresh = token_data.get("refresh_token")
                    expires_in = token_data.get("expires_in")
                    new_expires_at = (
                        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                        if expires_in else datetime.now(timezone.utc) + timedelta(days=30)
                    )

                    token_rec.encrypted_access_token = encrypt_token(new_access)
                    if new_refresh:
                        # Provider rotated the refresh token -- replace the stored one.
                        token_rec.encrypted_refresh_token = encrypt_token(new_refresh)
                    # else: provider didn't return a new refresh token (e.g. Google's
                    # normal behavior) -- preserve the existing encrypted refresh token as-is.
                    token_rec.expires_at = new_expires_at
                    await self.session.commit()
                    # Postgres's set_config(..., is_local=true) resets whatever RLS context
                    # (bypass or a specific tenant) was active at the end of a transaction --
                    # re-assert this token's own organization as the tenant context so the
                    # caller's subsequent reads/writes for this exact org keep working. This
                    # is always correct: a caller already scoped to this org (the normal
                    # per-request case) sees no change, and a system job operating under a
                    # broader bypass (e.g. the Calendar poller) re-asserts its own bypass at
                    # the start of its next unit of work regardless.
                    from app.db.session import set_tenant_session_context
                    await set_tenant_session_context(self.session, organization_id)

                return decrypt_token(token_rec.encrypted_access_token)
        except TimeoutError as e:
            raise PermissionError(f"Could not acquire the OAuth refresh lock for provider '{provider}' in time; try again.") from e

    async def revoke_oauth_token(
        self,
        organization_id: UUID,
        provider: str,
        user_id: Optional[UUID] = None
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

        await AuditService(self.session).log(
            organization_id=organization_id,
            user_id=user_id,
            action="oauth:disconnect",
            details={"provider": p}
        )

        await self.session.commit()
        await self._broadcast_integration_status(organization_id, p, "disconnected")
        return True

    async def get_integration_statuses(self, organization_id: UUID) -> List[Dict[str, Any]]:
        """Connection status for every known provider, for the documented Connection
        Center dashboard's initial state (implementation_roadmap.md Milestone 6:
        "Frontend Tasks: Create Connection Center UI displaying available integrations
        and connect/disconnect buttons" -- the live WebSocket updates broadcast by
        _broadcast_integration_status keep it current after that). Never returns token
        material, and never triggers a live refresh call just to render a status view --
        status is read from already-persisted state (Integration.is_active,
        OAuthToken.expires_at), the same fields get_valid_oauth_token itself consults.

        GitHub, Slack, and Google Calendar are real per-organization OAuth connections in
        this codebase. Jira is not -- it authenticates via a single deployment-wide
        static API token (the same model jira_tools.py and the backup-sync poller already
        use), so its status reflects whether that global configuration is present, not a
        per-org OAuthToken row.
        """
        from sqlalchemy import select
        from datetime import datetime, timezone
        from app.core.config import settings
        from app.models.integration import Integration, OAuthToken

        oauth_providers = ["github", "slack", "google_calendar"]
        res = await self.session.execute(
            select(Integration, OAuthToken)
            .outerjoin(OAuthToken, OAuthToken.integration_id == Integration.id)
            .where(Integration.organization_id == organization_id, Integration.provider.in_(oauth_providers))
        )
        by_provider = {integration.provider: (integration, token) for integration, token in res.all()}

        now = datetime.now(timezone.utc)
        statuses: List[Dict[str, Any]] = []
        for provider in oauth_providers:
            entry = by_provider.get(provider)
            if not entry or not entry[0].is_active or not entry[1]:
                statuses.append({"provider": provider, "status": "disconnected", "updated_at": None})
                continue
            integration, token_rec = entry
            connection_status = "reauth_required" if (token_rec.expires_at and token_rec.expires_at <= now) else "connected"
            statuses.append({"provider": provider, "status": connection_status, "updated_at": integration.updated_at.isoformat()})

        jira_configured = bool(settings.JIRA_BASE_URL and settings.JIRA_API_TOKEN and settings.JIRA_EMAIL)
        statuses.append({"provider": "jira", "status": "connected" if jira_configured else "disconnected", "updated_at": None})

        return statuses

    async def run_backup_sync(self, integration_id: UUID) -> int:
        """Delta-sync backup poll for a single active integration, per
        system_architecture_design.md's Sync frequency matrix ("Jira = webhook + 4-hour backup
        cron"). Currently implemented for Jira only — GitHub's documented backup cron additionally
        needs to know which repositories to poll, and there is no "link repository" endpoint or
        any populated `repositories` row anywhere in this codebase yet to resolve that from, so
        it is intentionally out of scope here rather than guessing at a repo list. Slack is
        documented as webhook-only (no polling), so it never needs a backup sync at all.

        Returns the number of items ingested into the outbox as new Events.
        """
        from sqlalchemy import select
        from datetime import datetime, timezone
        from app.core.config import settings
        from app.models.integration import Integration

        integration = await self.session.get(Integration, integration_id)
        if not integration or not integration.is_active:
            return 0
        if integration.provider != "jira":
            return 0

        connector = JiraConnector(
            domain=(settings.JIRA_BASE_URL.split("//")[-1].split(".")[0] if settings.JIRA_BASE_URL and settings.JIRA_BASE_URL.startswith("http") else settings.JIRA_BASE_URL),
            api_token=settings.JIRA_API_TOKEN,
            user_email=settings.JIRA_EMAIL,
        )
        issues = await connector.search_recently_updated_issues(since=integration.last_synced_at)

        ingested = 0
        for issue in issues:
            fields = issue.get("fields", {})
            db_event = Event(
                organization_id=integration.organization_id,
                routing_key="jira:issue_synced",
                payload={
                    "routing_key": "jira:issue_synced",
                    "provider": "jira",
                    "issue_key": issue.get("key"),
                    "project_key": (fields.get("project") or {}).get("key"),
                    "summary": fields.get("summary"),
                    "status": (fields.get("status") or {}).get("name"),
                    "source": "backup_sync",
                },
                processed=False,
            )
            self.session.add(db_event)
            ingested += 1

        integration.last_synced_at = datetime.now(timezone.utc)
        await self.session.commit()
        return ingested

    async def run_backup_sync_all(self) -> Dict[str, int]:
        """Run the backup delta-sync poll across every active Jira integration in every
        organization — the actual periodic job the background worker calls. Requires an RLS
        bypass since this is a system-initiated job with no single tenant's request context,
        the same documented carve-out implementation_rules.md describes for SuperAdmin/system
        actions (app.bypass_rls, scoped to this transaction only)."""
        from sqlalchemy import select
        from app.models.integration import Integration
        from app.db.session import set_bypass_rls_context

        await set_bypass_rls_context(self.session)
        res = await self.session.execute(
            select(Integration).where(Integration.provider == "jira", Integration.is_active == True)
        )
        integrations = res.scalars().all()

        results: Dict[str, int] = {}
        for integration in integrations:
            try:
                count = await self.run_backup_sync(integration.id)
                results[str(integration.id)] = count
            except Exception:
                results[str(integration.id)] = -1  # sync failed for this integration; continue with the rest
        return results

    async def get_jira_projects(self) -> List[Dict[str, str]]:
        """Import Jira Projects List (api_contract.md section 5.A). Uses the real Jira REST
        API v3 through the same static-credential connector construction already
        established for Jira elsewhere in this codebase (run_backup_sync, jira_tools) --
        Jira in this system authenticates via a configured API token/email (Basic Auth),
        not per-tenant OAuth. No consumer anywhere resolves Jira credentials through
        get_valid_oauth_token, so this method deliberately doesn't either, to avoid
        introducing a second, inconsistent Jira auth model. Raises ValueError if Jira
        credentials aren't configured; httpx errors from the provider propagate unwrapped
        for the caller to handle.
        """
        from app.core.config import settings

        connector = JiraConnector(
            domain=(settings.JIRA_BASE_URL.split("//")[-1].split(".")[0] if settings.JIRA_BASE_URL and settings.JIRA_BASE_URL.startswith("http") else settings.JIRA_BASE_URL),
            api_token=settings.JIRA_API_TOKEN,
            user_email=settings.JIRA_EMAIL,
        )
        raw_projects = await connector.list_projects()
        return [{"key": p["key"], "name": p["name"]} for p in raw_projects if p.get("key") and p.get("name")]

    async def link_github_repository(
        self,
        organization_id: UUID,
        project_id: UUID,
        external_repo_id: str,
        name: str,
        clone_url: str,
        user_id: Optional[UUID] = None,
    ) -> Repository:
        """Link a GitHub repository to a project (api_contract.md section 4.A). This is the
        prerequisite the documented GitHub backup-sync cron needs (it must know which
        repositories to poll) and was previously entirely missing — the `repositories` table
        existed in the schema but nothing ever wrote to it.

        Raises ValueError if the project doesn't exist or belongs to a different organization.
        """
        project = await self.session.get(Project, project_id)
        if not project or project.organization_id != organization_id:
            raise ValueError("Project not found in this organization.")

        existing = await self.session.execute(
            select(Repository).where(
                Repository.project_id == project_id,
                Repository.external_repo_id == external_repo_id,
            )
        )
        repo = existing.scalar_one_or_none()
        if repo:
            repo.name = name
            repo.clone_url = clone_url
        else:
            repo = Repository(
                organization_id=organization_id,
                project_id=project_id,
                external_repo_id=external_repo_id,
                name=name,
                clone_url=clone_url,
            )
            self.session.add(repo)

        # clone_url is deliberately excluded from the audit details -- an authenticated
        # clone URL can embed a credential (e.g. https://<token>@github.com/...), unlike
        # the repo name/external_repo_id which are safe public identifiers.
        await AuditService(self.session).log(
            organization_id=organization_id,
            user_id=user_id,
            action="repository:link",
            details={"provider": "github", "project_id": str(project_id), "external_repo_id": external_repo_id, "name": name}
        )

        await self.session.commit()
        await self.session.refresh(repo)
        return repo

    async def discover_github_repositories(self, organization_id: UUID) -> List[Dict[str, Any]]:
        """List real repositories the organization's connected GitHub token can access, per
        api_contract.md section 4.A's "select GitHub repositories to link" step -- this is
        what a PM actually browses before calling link_github_repository, as opposed to
        needing to already know a repo's exact id/name/clone_url. Raises ValueError if GitHub
        isn't connected for this organization.
        """
        from app.integrations.github import GitHubConnector

        token = await self.get_valid_oauth_token(organization_id, "github")
        if not token:
            raise ValueError("GitHub is not connected for this organization. Connect it first via /oauth/github/authorize.")

        connector = GitHubConnector(token=token)
        repos = await connector.list_repositories()
        return [
            {
                "external_repo_id": str(r["id"]),
                "name": r["full_name"],
                "clone_url": r["clone_url"],
                "private": r.get("private", False),
                "default_branch": r.get("default_branch"),
                "updated_at": r.get("updated_at"),
            }
            for r in repos
        ]

    async def list_linked_repositories(self, organization_id: UUID, project_id: UUID) -> List[Repository]:
        """List repositories already linked (via link_github_repository) to a project --
        distinct from discover_github_repositories, which lists what COULD be linked. Raises
        ValueError if the project doesn't exist / belongs to another organization.
        """
        project = await self.session.get(Project, project_id)
        if not project or project.organization_id != organization_id:
            raise ValueError("Project not found in this organization.")

        res = await self.session.execute(
            select(Repository).where(Repository.project_id == project_id, Repository.organization_id == organization_id)
        )
        return list(res.scalars().all())

    async def sync_calendar_events(
        self,
        organization_id: UUID,
        project_id: UUID,
        start_date: "datetime",
        end_date: "datetime",
    ) -> Dict[str, Any]:
        """Sync Calendar Events Range (api_contract.md section 7.A). Calendar is documented as
        polling-driven (not webhook-driven like GitHub/Jira/Slack) per
        detailed_component_architecture.md's Sync Frequency Matrix, so this endpoint is
        Calendar's only real data-ingestion path — the existing google/webhook receiver only
        ever stores a change signal, never the actual event data.

        Raises LookupError if the project doesn't exist / belongs to another org, ValueError
        if the organization has no active Google Calendar OAuth connection, or
        PermissionError if the connection's access token has expired and could not be
        refreshed (no refresh token available, or the provider rejected it) -- both raised
        by get_valid_oauth_token(), the single place expiry/refresh is handled so this
        method (and every other OAuth consumer) doesn't duplicate that logic.
        """
        from datetime import datetime as dt
        from app.models.project import Meeting

        project = await self.session.get(Project, project_id)
        if not project or project.organization_id != organization_id:
            raise LookupError("Project not found in this organization.")

        access_token = await self.get_valid_oauth_token(organization_id, "google_calendar")
        if not access_token:
            raise ValueError("No active Google Calendar connection for this organization. Authorize via /oauth/google_calendar/authorize first.")

        connector = GoogleCalendarConnector(access_token=access_token)
        events = await connector.list_events(time_min=start_date, time_max=end_date)

        synced = 0
        for ev in events:
            external_id = ev.get("id")
            if not external_id:
                continue
            start_raw = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
            end_raw = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date")
            if not start_raw or not end_raw:
                continue
            start_time = dt.fromisoformat(start_raw.replace("Z", "+00:00"))
            end_time = dt.fromisoformat(end_raw.replace("Z", "+00:00"))
            attendees = [a.get("email") for a in (ev.get("attendees") or []) if a.get("email")]
            title = ev.get("summary") or "Untitled Event"

            existing = await self.session.execute(
                select(Meeting).where(Meeting.project_id == project_id, Meeting.external_event_id == external_id)
            )
            meeting = existing.scalar_one_or_none()
            if meeting:
                meeting.title = title
                meeting.start_time = start_time
                meeting.end_time = end_time
                meeting.attendees = attendees
            else:
                meeting = Meeting(
                    organization_id=organization_id,
                    project_id=project_id,
                    external_event_id=external_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    attendees=attendees,
                )
                self.session.add(meeting)
            synced += 1

        await self.session.commit()
        return {"events_synced": synced, "events_found": len(events)}

    async def create_calendar_event(
        self,
        organization_id: UUID,
        project_id: UUID,
        title: str,
        start_time: "datetime",
        end_time: "datetime",
        attendee_emails: Optional[List[str]] = None,
        description: str = "",
        user_id: Optional[UUID] = None,
    ) -> Meeting:
        """Schedule a real Google Calendar event -- the write side sync_calendar_events never
        had, per the product vision's "PM should be able to organize/schedule meetings from
        AI-TPM" requirement. Uses the existing `calendar.events` OAuth scope already granted;
        that scope covers write as well as read, so no additional consent/re-authorization is
        needed. Persists the resulting Meeting row immediately (rather than waiting for the
        next poll) so it shows up in GET /calendar/meetings right away.

        Raises LookupError if the project doesn't exist / belongs to another org, ValueError
        if the organization has no active Google Calendar connection, or PermissionError if
        the token has expired and couldn't be refreshed -- all via get_valid_oauth_token,
        matching sync_calendar_events's convention exactly.
        """
        project = await self.session.get(Project, project_id)
        if not project or project.organization_id != organization_id:
            raise LookupError("Project not found in this organization.")

        access_token = await self.get_valid_oauth_token(organization_id, "google_calendar")
        if not access_token:
            raise ValueError("No active Google Calendar connection for this organization. Authorize via /oauth/google_calendar/authorize first.")

        connector = GoogleCalendarConnector(access_token=access_token)
        event = await connector.create_event(
            summary=title,
            start_time=start_time,
            end_time=end_time,
            attendee_emails=attendee_emails,
            description=description,
        )

        external_id = event.get("id")
        if not external_id:
            raise ValueError("Google Calendar did not return an event id for the created event.")

        meeting = Meeting(
            organization_id=organization_id,
            project_id=project_id,
            external_event_id=external_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendee_emails or [],
        )
        self.session.add(meeting)

        await AuditService(self.session).log(
            organization_id=organization_id,
            user_id=user_id,
            action="calendar:event_create",
            details={"project_id": str(project_id), "title": title, "external_event_id": external_id},
        )

        await self.session.commit()
        await self.session.refresh(meeting)
        return meeting

    async def list_meetings(
        self,
        organization_id: UUID,
        project_id: UUID,
    ) -> List[Meeting]:
        """List Synced Calendar Meetings for a project (database_schema_design.md section 19
        `meetings` table; ui_ux_design.md section 10 Calendar page's documented "active meeting
        agendas list" widget). sync_calendar_events() has written real Meeting rows since it was
        implemented, but nothing ever read them back out -- this closes that gap.

        Raises LookupError if the project doesn't exist / belongs to another org, matching the
        same ownership-check convention as sync_calendar_events().
        """
        project = await self.session.get(Project, project_id)
        if not project or project.organization_id != organization_id:
            raise LookupError("Project not found in this organization.")

        res = await self.session.execute(
            select(Meeting)
            .where(Meeting.project_id == project_id, Meeting.organization_id == organization_id)
            .order_by(Meeting.start_time.asc())
        )
        return list(res.scalars().all())

    async def map_slack_channel_to_project(
        self,
        organization_id: UUID,
        project_id: UUID,
        slack_channel_id: str,
        user_id: Optional[UUID] = None,
    ) -> SlackChannelMapping:
        """Map Project to Slack Channel (api_contract.md section 6.A). Lets incoming Slack
        webhook messages be routed to the correct project by channel, per
        implementation_roadmap.md Milestone 9's documented "Slack channel-to-project mappings"
        deliverable — a channel maps to at most one project.

        Raises ValueError if the project doesn't exist / belongs to another org, or if the
        channel is already mapped to a project in a DIFFERENT organization (cross-tenant
        conflict — refuse rather than silently reassign another tenant's mapping).
        """
        project = await self.session.get(Project, project_id)
        if not project or project.organization_id != organization_id:
            raise LookupError("Project not found in this organization.")

        existing = await self.session.execute(
            select(SlackChannelMapping).where(SlackChannelMapping.slack_channel_id == slack_channel_id)
        )
        mapping = existing.scalar_one_or_none()
        if mapping:
            if mapping.organization_id != organization_id:
                raise ValueError(f"Slack channel '{slack_channel_id}' is already mapped to a project in a different organization.")
            mapping.project_id = project_id
        else:
            mapping = SlackChannelMapping(
                organization_id=organization_id,
                project_id=project_id,
                slack_channel_id=slack_channel_id,
            )
            self.session.add(mapping)

        await AuditService(self.session).log(
            organization_id=organization_id,
            user_id=user_id,
            action="slack:channel_map",
            details={"project_id": str(project_id), "slack_channel_id": slack_channel_id}
        )

        await self.session.commit()
        await self.session.refresh(mapping)
        return mapping

    async def discover_slack_channels(self, organization_id: UUID) -> List[Dict[str, Any]]:
        """List real channels the organization's connected Slack bot token can see, per
        api_contract.md section 6.A's "select Slack channels to map" step -- what a PM
        actually browses before calling map_slack_channel_to_project, as opposed to needing
        to already know a channel's exact id. Raises ValueError if Slack isn't connected.
        """
        from app.integrations.slack import SlackConnector

        token = await self.get_valid_oauth_token(organization_id, "slack")
        if not token:
            raise ValueError("Slack is not connected for this organization. Connect it first via /oauth/slack/authorize.")

        connector = SlackConnector(bot_token=token)
        channels = await connector.list_channels()
        return [
            {
                "slack_channel_id": c["id"],
                "name": c.get("name", ""),
                "is_private": c.get("is_private", False),
                "num_members": c.get("num_members", 0),
                "topic": (c.get("topic") or {}).get("value", ""),
            }
            for c in channels
        ]

    async def list_mapped_channels(self, organization_id: UUID, project_id: UUID) -> List[SlackChannelMapping]:
        """List Slack channels already mapped to a project -- distinct from
        discover_slack_channels, which lists what COULD be mapped. Raises ValueError if the
        project doesn't exist / belongs to another organization."""
        project = await self.session.get(Project, project_id)
        if not project or project.organization_id != organization_id:
            raise ValueError("Project not found in this organization.")

        res = await self.session.execute(
            select(SlackChannelMapping).where(SlackChannelMapping.project_id == project_id, SlackChannelMapping.organization_id == organization_id)
        )
        return list(res.scalars().all())

    async def resolve_project_for_slack_channel(self, organization_id: UUID, slack_channel_id: str) -> Optional[UUID]:
        """Look up the project a Slack channel is mapped to, for auto-routing incoming webhook
        messages when the caller doesn't explicitly pass a project_id."""
        if not slack_channel_id:
            return None
        res = await self.session.execute(
            select(SlackChannelMapping).where(
                SlackChannelMapping.organization_id == organization_id,
                SlackChannelMapping.slack_channel_id == slack_channel_id,
            )
        )
        mapping = res.scalar_one_or_none()
        return mapping.project_id if mapping else None

    async def get_active_calendar_integrations(self) -> List[Tuple[UUID, UUID]]:
        """Discover every organization with an active Google Calendar OAuth connection --
        the tenant-discovery step for the periodic Calendar poller
        (implementation_roadmap.md Milestone 10: "Poller running every 15 minutes fetching
        updated meetings"). System job with no single tenant's request context, RLS-bypassed
        via the same documented carve-out used by run_backup_sync_all for Jira. Returns
        (integration_id, organization_id) pairs only -- no credential material.
        """
        from app.models.integration import Integration
        from app.db.session import set_bypass_rls_context

        await set_bypass_rls_context(self.session)
        res = await self.session.execute(
            select(Integration).where(Integration.provider == "google_calendar", Integration.is_active == True)
        )
        return [(i.id, i.organization_id) for i in res.scalars().all()]

    async def run_calendar_poll_sync(self, integration_id: UUID) -> Dict[str, int]:
        """Poll one organization's connected Google Calendar across every one of its
        projects, reusing sync_calendar_events() -- the exact same synchronization logic the
        manual POST /calendar/sync endpoint uses -- so both paths behave identically. Uses
        the integration's last_synced_at watermark (the same column/pattern already
        established for the Jira backup-sync poller) as the sync window's lower bound, so
        back-to-back poll cycles don't re-fetch the same range or leave gaps if a cycle is
        skipped/delayed.

        A fresh call to set_bypass_rls_context is issued before every read/write in this
        method: sync_calendar_events() commits per project, and Postgres's
        set_config(..., is_local=true) resets at the end of each transaction, so the bypass
        must be re-asserted after every commit/rollback rather than once at the top.

        Raises PermissionError if the org's Calendar OAuth token has expired (propagated
        immediately without looping through remaining projects, since they all share the
        same org-level token and would fail identically). Individual per-project failures
        are caught and recorded as -1 so one bad project doesn't stop the others; the
        integration's watermark only advances after every project succeeds.
        """
        from datetime import datetime, timedelta, timezone
        from app.models.integration import Integration
        from app.db.session import set_bypass_rls_context

        await set_bypass_rls_context(self.session)
        integration = await self.session.get(Integration, integration_id)
        if not integration or not integration.is_active or integration.provider != "google_calendar":
            return {}

        now = datetime.now(timezone.utc)
        time_min = integration.last_synced_at or (now - timedelta(hours=1))
        time_max = now + timedelta(days=30)

        await set_bypass_rls_context(self.session)
        projects_res = await self.session.execute(
            select(Project).where(Project.organization_id == integration.organization_id, Project.deleted_at == None)
        )
        projects = projects_res.scalars().all()

        results: Dict[str, int] = {}
        for project in projects:
            project_id_str = str(project.id)
            await set_bypass_rls_context(self.session)
            try:
                result = await self.sync_calendar_events(
                    organization_id=integration.organization_id,
                    project_id=project.id,
                    start_date=time_min,
                    end_date=time_max,
                )
                results[project_id_str] = result["events_synced"]
            except PermissionError:
                await self.session.rollback()
                raise
            except Exception:
                # A rollback expires every ORM instance attached to this session (including
                # `integration`, read further below) -- re-fetch it before touching it again
                # rather than risk a lazy-load attempt outside an awaited context.
                await self.session.rollback()
                results[project_id_str] = -1

        await set_bypass_rls_context(self.session)
        integration = await self.session.get(Integration, integration_id)
        integration.last_synced_at = now
        await self.session.commit()
        return results

