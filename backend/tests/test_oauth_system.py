import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from unittest.mock import patch

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.models.tenant import Organization
from app.models.integration import Integration, OAuthToken
from app.services.integration import IntegrationService
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


_real_async_client_post = httpx.AsyncClient.post


async def _fake_provider_post(self, url, **kwargs):
    """Stand in for the real provider token endpoint over HTTP (per
    engineering_handbook.md's testing pyramid: unit tests mock externals) — this test
    exercises OUR request construction and response parsing, not a real GitHub/Atlassian/
    Slack/Google server, which cannot be reached with a fabricated authorization code anyway.

    httpx.AsyncClient.post is patched at the class level, which also intercepts this same
    test's own ASGI-transport calls into the local FastAPI app (e.g. via
    create_authenticated_headers) — anything that isn't one of the two provider token
    endpoints under test must fall through to the real implementation."""
    fake_request = httpx.Request("POST", str(url))
    if "github.com/login/oauth/access_token" in str(url):
        assert kwargs["data"]["code"] == "test_auth_code_99"
        return httpx.Response(200, request=fake_request, json={"access_token": "gho_mocked_github_token_123", "token_type": "bearer", "scope": "repo,user"})
    if "auth.atlassian.com/oauth/token" in str(url):
        assert kwargs["json"]["code"] == "jira_auth_code_77"
        return httpx.Response(200, request=fake_request, json={
            "access_token": "atlassian_mocked_access_456", "refresh_token": "atlassian_mocked_refresh_789",
            "expires_in": 3600, "scope": "read:jira-work write:jira-work",
        })
    return await _real_async_client_post(self, url, **kwargs)

async def test_oauth_system_flow():
    print("Initializing OAuth System & Token Encryption validation tests...")

    # 1. Test AES-256 Fernet Encryption/Decryption Round-Trip
    print("\nTest 1: Testing AES-256 Fernet token encryption & decryption...")
    raw_secret = "gho_16678239847239874928374982374982"
    encrypted = encrypt_token(raw_secret)
    assert encrypted != raw_secret
    decrypted = decrypt_token(encrypted)
    assert decrypted == raw_secret
    print("SUCCESS: Fernet token encryption and decryption verified.")

    # 2. Test IntegrationService OAuth URL Generation
    print("\nTest 2: Testing OAuth authorize URL generation...")
    async with SessionLocal() as session:
        service = IntegrationService(session)
        org_id = uuid.uuid4()
        gh_url = await service.generate_oauth_authorize_url("github", org_id, "http://localhost:3000/callback")
        jira_url = await service.generate_oauth_authorize_url("jira", org_id, "http://localhost:3000/callback")
        slack_url = await service.generate_oauth_authorize_url("slack", org_id, "http://localhost:3000/callback")
        google_url = await service.generate_oauth_authorize_url("google", org_id, "http://localhost:3000/callback")

        assert "github.com/login/oauth/authorize" in gh_url
        assert "auth.atlassian.com" in jira_url
        assert "slack.com/oauth/v2/authorize" in slack_url
        assert "accounts.google.com" in google_url
        print("SUCCESS: OAuth authorization URLs generated successfully.")

    # 3. Test Code Exchange & Encrypted DB Persistence (real HTTP request/response handling,
    # with the actual provider endpoint mocked at the transport layer — see _fake_provider_post)
    print("\nTest 3: Testing OAuth code exchange & encrypted DB persistence...")
    test_org_id = None
    created_org_ids = []

    # Configure fake-but-present client credentials so exchange_code_for_token doesn't
    # short-circuit on "not configured" (restored in the finally block below).
    original_creds = (
        settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET,
        settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET,
    )
    settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET = "test_gh_client_id", "test_gh_client_secret"
    settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET = "test_jira_client_id", "test_jira_client_secret"

    try:
        with patch.object(httpx.AsyncClient, "post", new=_fake_provider_post):
            async with SessionLocal() as session:
                service = IntegrationService(session)

                # Create test org
                org = Organization(name=f"OAuth Test Org {uuid.uuid4().hex[:6]}", domain=f"oauth-{uuid.uuid4().hex[:6]}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                created_org_ids.append(test_org_id)
                await session.commit()

                # Exchange code for token — this now makes a real httpx POST (to the mocked
                # transport) rather than fabricating a token string internally.
                res = await service.exchange_code_for_token(
                    provider="github",
                    code="test_auth_code_99",
                    organization_id=test_org_id,
                    redirect_uri="http://localhost:3000/callback"
                )
                assert res["status"] == "connected"
                assert res["provider"] == "github"

                # Verify the exact token returned by the (mocked) provider round-trips through
                # encryption/storage/decryption unchanged — not a fabricated "provider_token_<code>" string.
                dec_token = await service.get_valid_oauth_token(test_org_id, "github")
                assert dec_token == "gho_mocked_github_token_123"
                print("SUCCESS: Real request construction, response parsing, encrypted DB persistence, and token decryption all verified.")

            # 4. Test HTTP OAuth Endpoints
            print("\nTest 4: Testing OAuth HTTP REST API endpoints...")
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                auth_headers = await create_authenticated_headers(client, test_org_id)

                # Authorize endpoint
                res = await client.get("/api/v1/integrations/oauth/github/authorize", headers=auth_headers)
                assert res.status_code == 200
                assert "authorization_url" in res.json()

                # Callback endpoint — exchanges against the mocked Jira token endpoint
                res = await client.get("/api/v1/integrations/oauth/jira/callback?code=jira_auth_code_77", headers=auth_headers)
                assert res.status_code == 200
                assert res.json()["status"] == "connected"

                # Retrieve active token endpoint — must be the provider's real (mocked) token value
                res = await client.get(f"/api/v1/integrations/oauth/tokens/{test_org_id}?provider=jira", headers=auth_headers)
                assert res.status_code == 200
                assert res.json()["access_token"] == "atlassian_mocked_access_456"

                # Revoke integration endpoint
                res = await client.delete("/api/v1/integrations/oauth/jira", headers=auth_headers)
                assert res.status_code == 200
                assert res.json()["status"] == "revoked"
                print("SUCCESS: OAuth HTTP API endpoints verified end-to-end against the mocked provider.")

    finally:
        # Restore real (unset) client credentials
        (settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET,
         settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET) = original_creds

        # Clean up test records
        print("\nCleaning up OAuth test database records...")
        async with SessionLocal() as session:
            for oid in created_org_ids:
                tok_res = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == oid))
                for tok in tok_res.scalars().all():
                    await session.delete(tok)
                int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                for integ in int_res.scalars().all():
                    await session.delete(integ)
                org_res = await session.execute(select(Organization).where(Organization.id == oid))
                db_org = org_res.scalar_one_or_none()
                if db_org:
                    await session.delete(db_org)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll OAuth System & Token Encryption tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_oauth_system_flow())
