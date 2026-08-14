import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.core.security import encrypt_token
from app.models.tenant import Organization, User
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


_real_async_client_post = httpx.AsyncClient.post


async def _fake_google_oauth_post(self, url, **kwargs):
    if "oauth2.googleapis.com/token" not in str(url):
        return await _real_async_client_post(self, url, **kwargs)
    return httpx.Response(200, request=httpx.Request("POST", str(url)), json={
        "access_token": "ya29.connection_center_test_secret", "refresh_token": "1//connection_center_refresh_secret",
        "expires_in": 3600, "scope": "https://www.googleapis.com/auth/calendar.events",
    })


async def test_connection_center_oauth_flow():
    print("Initializing Connection Center OAuth (Slack/Jira/Google Calendar) validation tests...")

    org_ids = []
    original_google_creds = (settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET)
    original_jira = (settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)
    settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET = "test_google_client_id", "test_google_client_secret"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Connection Center Org A {uuid.uuid4().hex[:6]}", domain=f"ccenter-a-{uuid.uuid4().hex[:6]}.com")
                org_b = Organization(name=f"Connection Center Org B {uuid.uuid4().hex[:6]}", domain=f"ccenter-b-{uuid.uuid4().hex[:6]}.com")
                session.add_all([org_a, org_b])
                await session.commit()
            org_ids.extend([org_a.id, org_b.id])
            headers_a = await create_authenticated_headers(client, org_a.id)
            headers_b = await create_authenticated_headers(client, org_b.id)

            # 1. Google Calendar authorize URL generation, via the SAME generic endpoint
            # the new Connection Center's Connect button calls -- no client secret ever
            # appears in the response.
            print("\nTest 1: Verifying the generic OAuth authorize endpoint works for google_calendar...")
            res = await client.get("/api/v1/integrations/oauth/google_calendar/authorize", headers=headers_a)
            assert res.status_code == 200, res.text
            auth_url = res.json()["authorization_url"]
            assert "accounts.google.com" in auth_url
            assert "test_google_client_secret" not in auth_url, "Client secret must never appear in the authorize URL"
            print("SUCCESS: google_calendar authorize URL generated with no leaked client secret.")

            # 2. Completing the OAuth exchange (mocked provider) via the generic callback
            # endpoint must succeed, and the status endpoint must reflect 'connected' with
            # zero credential material anywhere in the response.
            print("\nTest 2: Verifying the generic OAuth callback connects google_calendar and status reflects it...")
            with patch.object(httpx.AsyncClient, "post", new=_fake_google_oauth_post):
                res = await client.get("/api/v1/integrations/oauth/google_calendar/callback?code=cc-test-code", headers=headers_a)
            assert res.status_code == 200, res.text
            assert res.json()["status"] == "connected"
            assert "ya29.connection_center_test_secret" not in res.text
            assert "1//connection_center_refresh_secret" not in res.text

            res = await client.get("/api/v1/integrations/status", headers=headers_a)
            calendar_status = next(i for i in res.json()["integrations"] if i["provider"] == "google_calendar")
            assert calendar_status["status"] == "connected"
            assert "ya29" not in res.text and "connection_center_test_secret" not in res.text
            print("SUCCESS: google_calendar connected via the generic OAuth flow; status reflects it with no leaked tokens.")

            # 3. Cross-tenant isolation: Org B must see google_calendar as disconnected,
            # completely unaffected by Org A's connection.
            print("\nTest 3: Verifying Org B's status is unaffected by Org A's Calendar connection...")
            res_b = await client.get("/api/v1/integrations/status", headers=headers_b)
            calendar_status_b = next(i for i in res_b.json()["integrations"] if i["provider"] == "google_calendar")
            assert calendar_status_b["status"] == "disconnected"
            print("SUCCESS: Org B correctly isolated from Org A's Calendar connection.")

            # 4. Revoking via the generic DELETE endpoint must flip status back to
            # 'disconnected', with no token material in the response.
            print("\nTest 4: Verifying the generic revoke endpoint disconnects google_calendar...")
            res = await client.delete("/api/v1/integrations/oauth/google_calendar", headers=headers_a)
            assert res.status_code == 200, res.text
            assert res.json()["status"] == "revoked"
            res = await client.get("/api/v1/integrations/status", headers=headers_a)
            calendar_status = next(i for i in res.json()["integrations"] if i["provider"] == "google_calendar")
            assert calendar_status["status"] == "disconnected"
            print("SUCCESS: google_calendar correctly disconnected via the generic revoke endpoint.")

            # 5. Jira's status must reflect the deployment's static credential configuration
            # ONLY -- never a per-org OAuthToken row, even if one technically exists (the
            # Connection Center intentionally renders Jira as status-only, not
            # Connect/Disconnect, precisely because a per-org OAuthToken here would be
            # misleading: nothing in this codebase's Jira tools/backup-sync ever reads it).
            print("\nTest 5: Verifying Jira status reflects global config, not a stray per-org OAuthToken row...")
            settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = None, None, None
            async with SessionLocal() as session:
                stray_integration = Integration(organization_id=org_a.id, provider="jira", is_active=True)
                session.add(stray_integration)
                await session.flush()
                stray_token = OAuthToken(
                    organization_id=org_a.id, integration_id=stray_integration.id,
                    encrypted_access_token=encrypt_token("stray-jira-token-never-used"),
                )
                session.add(stray_token)
                await session.commit()

            res = await client.get("/api/v1/integrations/status", headers=headers_a)
            jira_status = next(i for i in res.json()["integrations"] if i["provider"] == "jira")
            assert jira_status["status"] == "disconnected", (
                "Jira status must reflect the (unset) global JIRA_* settings, not the stray per-org OAuthToken row"
            )

            settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = "acme-cc-test", "bot@acme-cc-test.com", "cc-test-token"
            res = await client.get("/api/v1/integrations/status", headers=headers_a)
            jira_status = next(i for i in res.json()["integrations"] if i["provider"] == "jira")
            assert jira_status["status"] == "connected", "Jira status must flip to connected once the global settings are configured"
            print("SUCCESS: Jira status correctly reflects only the global deployment configuration.")

        finally:
            settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET = original_google_creds
            settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = original_jira

            print("\nCleaning up Connection Center OAuth test database entries...")
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

    print("\nAll Connection Center OAuth tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_connection_center_oauth_flow())
