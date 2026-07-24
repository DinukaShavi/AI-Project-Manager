import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.core.security import encrypt_token, decrypt_token
from app.models.tenant import Organization
from app.models.integration import Integration, OAuthToken
from app.services.integration import IntegrationService
from app.db.session import SessionLocal

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

    # 3. Test Code Exchange & Encrypted DB Persistence
    print("\nTest 3: Testing OAuth code exchange & encrypted DB persistence...")
    test_org_id = None
    created_org_ids = []

    async with SessionLocal() as session:
        service = IntegrationService(session)

        # Create test org
        org = Organization(name=f"OAuth Test Org {uuid.uuid4().hex[:6]}", domain=f"oauth-{uuid.uuid4().hex[:6]}.com")
        session.add(org)
        await session.flush()
        test_org_id = org.id
        created_org_ids.append(test_org_id)
        await session.commit()

        # Exchange code for token
        res = await service.exchange_code_for_token(
            provider="github",
            code="test_auth_code_99",
            organization_id=test_org_id,
            redirect_uri="http://localhost:3000/callback"
        )
        assert res["status"] == "connected"
        assert res["provider"] == "github"

        # Verify decrypted token retrieval
        dec_token = await service.get_valid_oauth_token(test_org_id, "github")
        assert dec_token == "github_access_token_test_aut"
        print("SUCCESS: Code exchange, encrypted DB persistence, and token decryption verified.")

    # 4. Test HTTP OAuth Endpoints
    print("\nTest 4: Testing OAuth HTTP REST API endpoints...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Authorize endpoint
            res = await client.get(f"/api/v1/integrations/oauth/github/authorize?organization_id={test_org_id}")
            assert res.status_code == 200
            assert "authorization_url" in res.json()

            # Callback endpoint
            res = await client.get(f"/api/v1/integrations/oauth/jira/callback?code=jira_auth_code_77&organization_id={test_org_id}")
            assert res.status_code == 200
            assert res.json()["status"] == "connected"

            # Retrieve active token endpoint
            res = await client.get(f"/api/v1/integrations/oauth/tokens/{test_org_id}?provider=jira")
            assert res.status_code == 200
            assert res.json()["access_token"] == "jira_access_token_jira_aut"

            # Revoke integration endpoint
            res = await client.delete(f"/api/v1/integrations/oauth/jira?organization_id={test_org_id}")
            assert res.status_code == 200
            assert res.json()["status"] == "revoked"
            print("SUCCESS: OAuth HTTP API endpoints verified.")

        finally:
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
