import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.models.tenant import Organization
from app.models.integration import Integration
from app.db.session import SessionLocal
from sqlalchemy import select
from tests._auth_helpers import create_authenticated_headers

_real_post = httpx.AsyncClient.post
_real_get = httpx.AsyncClient.get
JIRA_ACCOUNT_ID = "5b10a2844c20165700ede21g"
JIRA_SITE_ID = "cloud-site-id-abc123"
JIRA_SITE_NAME = "Acme Corp"
JIRA_SITE_URL = "https://acme-corp.atlassian.net"


async def _fake_jira_post(self, url, **kwargs):
    if "auth.atlassian.com/oauth/token" in str(url):
        req = httpx.Request("POST", str(url))
        return httpx.Response(200, request=req, json={
            "access_token": "mocked_jira_access_token", "refresh_token": "mocked_jira_refresh_token",
            "expires_in": 3600, "scope": "read:jira-work write:jira-work offline_access",
        })
    return await _real_post(self, url, **kwargs)


async def _fake_jira_get(self, url, **kwargs):
    if str(url) == "https://api.atlassian.com/me":
        req = httpx.Request("GET", str(url))
        return httpx.Response(200, request=req, json={"account_id": JIRA_ACCOUNT_ID, "name": "Jane Developer", "email": "jane@acme-corp.com"})
    if str(url) == "https://api.atlassian.com/oauth/token/accessible-resources":
        req = httpx.Request("GET", str(url))
        return httpx.Response(200, request=req, json=[{"id": JIRA_SITE_ID, "name": JIRA_SITE_NAME, "url": JIRA_SITE_URL, "scopes": ["read:jira-work"]}])
    return await _real_get(self, url, **kwargs)


async def test_jira_identity_resolution_flow():
    print("Initializing Jira Site & Identity Resolution validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None

    original_creds = (settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET)
    settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET = "test_jira_client_id", "test_jira_client_secret"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Jira Identity Org A {suffix}", domain=f"jiraid-a-{suffix}.com")
                session.add(org_a)
                await session.commit()
                org_a_id = org_a.id

            headers_a = await create_authenticated_headers(client, org_a_id)

            with patch.object(httpx.AsyncClient, "post", new=_fake_jira_post), patch.object(httpx.AsyncClient, "get", new=_fake_jira_get):
                # 1. Connecting Jira resolves and stores the real connected site.
                print("\nTest 1: Verifying Jira OAuth connect resolves the real accessible site...")
                res = await client.get("/api/v1/integrations/oauth/jira/callback?code=fake_jira_code", headers=headers_a)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

                async with SessionLocal() as session:
                    int_res = await session.execute(select(Integration).where(Integration.organization_id == org_a_id, Integration.provider == "jira"))
                    integration = int_res.scalar_one()
                    assert integration.external_workspace_id == JIRA_SITE_ID
                    assert integration.external_workspace_name == JIRA_SITE_NAME
                print(f"SUCCESS: Real Jira site captured: {JIRA_SITE_NAME} ({JIRA_SITE_ID}).")

                # 2. The connecting user's real Jira account (accountId) is auto-linked.
                print("\nTest 2: Verifying the connecting user's real Jira identity was linked...")
                res = await client.get("/api/v1/organizations/external-identities/me", headers=headers_a)
                assert res.status_code == 200
                jira_identity = next((i for i in res.json()["identities"] if i["provider"] == "jira"), None)
                assert jira_identity is not None, "Expected a real auto-created Jira identity"
                assert jira_identity["external_account_id"] == JIRA_ACCOUNT_ID
                assert jira_identity["external_display_name"] == "Jane Developer"
                print(f"SUCCESS: Real Jira identity linked: accountId={JIRA_ACCOUNT_ID}.")

                # 3. Credential material never appears anywhere in the response.
                print("\nTest 3: Verifying no credential material leaks into the identity response...")
                assert "mocked_jira_access_token" not in res.text
                assert "mocked_jira_refresh_token" not in res.text
                print("SUCCESS: No token material present in the identity API response.")

        finally:
            print("\nCleaning up Jira identity resolution test database entries...")
            settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET = original_creds
            async with SessionLocal() as session:
                from app.models.external_identity import ExternalIdentity
                from app.models.integration import OAuthToken
                from app.models.tenant import User
                for oid in [o for o in [org_a_id] if o]:
                    for model in [ExternalIdentity, OAuthToken]:
                        res_db = await session.execute(select(model).where(model.organization_id == oid))
                        for row in res_db.scalars().all():
                            await session.delete(row)
                    await session.commit()

                    int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                    for i in int_res.scalars().all():
                        await session.delete(i)
                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()

                    org_row = await session.get(Organization, oid)
                    if org_row:
                        await session.delete(org_row)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Jira Site & Identity Resolution tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_jira_identity_resolution_flow())
