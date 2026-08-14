import asyncio
import uuid
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.core.security import encrypt_token
from app.realtime.connection_manager import ConnectionManager
from app.models.tenant import Organization, User
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from app.services.integration import IntegrationService
from tests._auth_helpers import create_authenticated_headers


class _FakeWebSocket:
    """Minimal stand-in for fastapi.WebSocket, recording every JSON frame it would have
    been sent -- used to test ConnectionManager delivery/isolation without a real live
    socket or TestClient's sync/threaded WebSocket transport."""

    def __init__(self):
        self.sent: list = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.sent.append(message)


_real_async_client_post = httpx.AsyncClient.post


async def _fake_github_oauth_post(self, url, **kwargs):
    if "github.com/login/oauth/access_token" not in str(url):
        return await _real_async_client_post(self, url, **kwargs)
    return httpx.Response(200, request=httpx.Request("POST", str(url)), json={
        "access_token": "gho_realtime_test_secret_token", "token_type": "bearer", "scope": "repo",
    })


async def test_integration_realtime_status_flow():
    print("Initializing Real-Time Integration Connection Status validation tests...")

    org_ids = []
    original_creds = (settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET)
    original_jira = (settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)
    settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET = "test_gh_client_id", "test_gh_client_secret"
    settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = None, None, None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Realtime Status Org A {uuid.uuid4().hex[:6]}", domain=f"rtstatus-a-{uuid.uuid4().hex[:6]}.com")
                session.add(org_a)
                await session.commit()
            org_ids.append(org_a.id)
            headers_a = await create_authenticated_headers(client, org_a.id)

            # 1. A fresh organization with no configured Jira and no OAuth connections must
            # report every provider as disconnected -- never fabricated "connected" data.
            print("\nTest 1: Verifying initial status for a fully disconnected organization...")
            res = await client.get("/api/v1/integrations/status", headers=headers_a)
            assert res.status_code == 200
            body = res.json()
            assert body["organization_id"] == str(org_a.id)
            statuses = {i["provider"]: i["status"] for i in body["integrations"]}
            assert statuses == {"github": "disconnected", "slack": "disconnected", "google_calendar": "disconnected", "jira": "disconnected"}
            print("SUCCESS: Fresh organization correctly reports every provider as disconnected.")

            # 2. Unauthenticated requests must be rejected.
            print("\nTest 2: Verifying the status endpoint requires authentication...")
            res = await client.get("/api/v1/integrations/status")
            assert res.status_code == 401
            print("SUCCESS: Unauthenticated request correctly rejected with 401.")

            # 3. Connecting an integration (real OAuth code exchange, mocked provider) must
            # broadcast a "connected" status update to the org's WebSocket channel, with no
            # credential material in the payload, AND the status endpoint must then reflect it.
            print("\nTest 3: Verifying a successful OAuth connection broadcasts 'connected' with no leaked credentials...")
            fake_manager = AsyncMock()
            with patch("app.realtime.connection_manager.get_connection_manager", return_value=fake_manager):
                with patch.object(httpx.AsyncClient, "post", new=_fake_github_oauth_post):
                    async with SessionLocal() as session:
                        service = IntegrationService(session)
                        result = await service.exchange_code_for_token(
                            provider="github", code="realtime-test-code", organization_id=org_a.id,
                            redirect_uri="http://localhost:3000/callback",
                        )
            assert result["status"] == "connected"
            assert fake_manager.broadcast_to_organization.await_count == 1
            broadcast_call = fake_manager.broadcast_to_organization.await_args
            broadcast_payload, broadcast_org = broadcast_call.args
            assert broadcast_org == org_a.id
            assert broadcast_payload["event"] == "integration_status_update"
            assert broadcast_payload["payload"]["provider"] == "github"
            assert broadcast_payload["payload"]["status"] == "connected"
            assert "timestamp" in broadcast_payload["payload"]
            serialized = str(broadcast_payload)
            assert "gho_realtime_test_secret_token" not in serialized, "Raw access token must never appear in a broadcast payload"
            print("SUCCESS: OAuth connection broadcast 'connected' with no credential material, scoped to the correct org.")

            res = await client.get("/api/v1/integrations/status", headers=headers_a)
            assert res.json()["integrations"]
            github_status = next(i for i in res.json()["integrations"] if i["provider"] == "github")
            assert github_status["status"] == "connected"
            print("SUCCESS: Status endpoint reflects the newly-connected GitHub integration.")

            # 4. Revoking must broadcast 'disconnected' and the status endpoint must reflect it.
            print("\nTest 4: Verifying revocation broadcasts 'disconnected'...")
            fake_manager_2 = AsyncMock()
            with patch("app.realtime.connection_manager.get_connection_manager", return_value=fake_manager_2):
                async with SessionLocal() as session:
                    service = IntegrationService(session)
                    revoked = await service.revoke_oauth_token(organization_id=org_a.id, provider="github")
            assert revoked is True
            assert fake_manager_2.broadcast_to_organization.await_count == 1
            payload2, org2 = fake_manager_2.broadcast_to_organization.await_args.args
            assert org2 == org_a.id
            assert payload2["payload"]["status"] == "disconnected"

            res = await client.get("/api/v1/integrations/status", headers=headers_a)
            github_status = next(i for i in res.json()["integrations"] if i["provider"] == "github")
            assert github_status["status"] == "disconnected"
            print("SUCCESS: Revocation broadcast 'disconnected'; status endpoint reflects it.")

            # 5. An expired token with no usable refresh token must broadcast
            # 'reauth_required' when discovered via get_valid_oauth_token, and the status
            # endpoint must independently reflect it too (from persisted expires_at, with
            # no live provider call required just to render the dashboard).
            print("\nTest 5: Verifying an unrefreshable expired token broadcasts 'reauth_required'...")
            async with SessionLocal() as session:
                integration = Integration(organization_id=org_a.id, provider="slack", is_active=True)
                session.add(integration)
                await session.flush()
                token_rec = OAuthToken(
                    organization_id=org_a.id, integration_id=integration.id,
                    encrypted_access_token=encrypt_token("expired-slack-access"),
                    encrypted_refresh_token="",
                    expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
                )
                session.add(token_rec)
                await session.commit()

            fake_manager_3 = AsyncMock()
            raised = False
            with patch("app.realtime.connection_manager.get_connection_manager", return_value=fake_manager_3):
                async with SessionLocal() as session:
                    try:
                        await IntegrationService(session).get_valid_oauth_token(org_a.id, "slack")
                    except PermissionError:
                        raised = True
            assert raised
            assert fake_manager_3.broadcast_to_organization.await_count == 1
            payload3, org3 = fake_manager_3.broadcast_to_organization.await_args.args
            assert org3 == org_a.id
            assert payload3["payload"]["provider"] == "slack"
            assert payload3["payload"]["status"] == "reauth_required"

            res = await client.get("/api/v1/integrations/status", headers=headers_a)
            slack_status = next(i for i in res.json()["integrations"] if i["provider"] == "slack")
            assert slack_status["status"] == "reauth_required"
            print("SUCCESS: Expired unrefreshable token broadcast 'reauth_required'; status endpoint independently agrees.")

            # 6. ConnectionManager itself must never cross-deliver one organization's
            # broadcast to another organization's connected clients (tenant isolation at
            # the transport layer, independent of anything above).
            print("\nTest 6: Verifying ConnectionManager never cross-delivers broadcasts between organizations...")
            org_b_id = uuid.uuid4()
            manager = ConnectionManager()
            ws_a = _FakeWebSocket()
            ws_b = _FakeWebSocket()
            await manager.connect(ws_a, org_a.id)
            await manager.connect(ws_b, org_b_id)

            await manager.broadcast_to_organization({"event": "integration_status_update", "payload": {"provider": "github", "status": "connected"}}, org_a.id)

            assert len(ws_a.sent) == 1, f"Expected org A's socket to receive exactly 1 message, got {len(ws_a.sent)}"
            assert len(ws_b.sent) == 0, "Org B's socket must NEVER receive org A's broadcast"
            assert ws_a.sent[0]["payload"]["provider"] == "github"
            print("SUCCESS: ConnectionManager correctly isolated the broadcast to org A only; org B received nothing.")

        finally:
            settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET = original_creds
            settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = original_jira

            print("\nCleaning up realtime integration status test database entries...")
            async with SessionLocal() as session:
                for oid in org_ids:
                    tok_res = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == oid))
                    for t in tok_res.scalars().all():
                        await session.delete(t)
                    int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                    for i in int_res.scalars().all():
                        await session.delete(i)
                    await session.commit()

                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()

                    org_res = await session.execute(select(Organization).where(Organization.id == oid))
                    db_org = org_res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Real-Time Integration Connection Status tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_integration_realtime_status_flow())
