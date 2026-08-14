import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from unittest.mock import patch

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.models.tenant import Organization, User, Role
from app.models.integration import Integration, OAuthToken
from app.models.external_identity import ExternalIdentity
from app.models.audit import AuditLog
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


_real_async_client_post = httpx.AsyncClient.post
SLACK_EXTERNAL_USER_ID = "U0EXTERNALTEST01"
SLACK_TEAM_ID = "T0EXTERNALTEST01"
SLACK_TEAM_NAME = "External Identity Test Workspace"


async def _fake_slack_post(self, url, **kwargs):
    """Real Slack oauth.v2.access response shape (authed_user.id + team.id/name are always
    present on a successful install, per api.slack.com/methods/oauth.v2.access) -- exercises
    our real extraction/parsing code, not a live Slack server."""
    if "slack.com/api/oauth.v2.access" in str(url):
        fake_request = httpx.Request("POST", str(url))
        return httpx.Response(200, request=fake_request, json={
            "ok": True,
            "access_token": "xoxb-mocked-bot-token",
            "token_type": "bot",
            "scope": "chat:write,channels:read,users:read",
            "bot_user_id": "U0BOTUSER01",
            "team": {"id": SLACK_TEAM_ID, "name": SLACK_TEAM_NAME},
            "authed_user": {"id": SLACK_EXTERNAL_USER_ID},
        })
    return await _real_async_client_post(self, url, **kwargs)


async def test_external_identity_flow():
    print("Initializing External Identity Foundation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    created_user_ids = []
    password = "ExtIdTestPass123!"

    original_creds = (settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET)
    settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET = "test_slack_client_id", "test_slack_client_secret"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"ExtId Org A {suffix}", domain=f"extid-a-{suffix}.com")
                org_b = Organization(name=f"ExtId Org B {suffix}", domain=f"extid-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id
                await session.commit()

            headers_a1 = await create_authenticated_headers(client, org_a_id)  # first Org A user
            headers_a2 = await create_authenticated_headers(client, org_a_id)  # second Org A user
            headers_b = await create_authenticated_headers(client, org_b_id)

            # OrgAdmin for Org A, for the RBAC-override unlink check.
            admin_email = f"extid-admin-{suffix}@example.com"
            async with SessionLocal() as session:
                admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                admin_user = User(organization_id=org_a_id, email=admin_email, full_name="ExtId Admin", hashed_password=get_password_hash(password))
                admin_user.roles.append(admin_role)
                session.add(admin_user)
                await session.commit()
            admin_login = await client.post("/api/v1/auth/login", json={"email": admin_email, "password": password})
            headers_admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

            with patch.object(httpx.AsyncClient, "post", new=_fake_slack_post):
                # 1. Connecting Slack auto-links the connecting user's real Slack identity.
                print("\nTest 1: Verifying Slack OAuth connect auto-creates an ExternalIdentity...")
                res = await client.get("/api/v1/integrations/oauth/slack/callback?code=fake_code_1", headers=headers_a1)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
                assert res.json()["status"] == "connected"

                res = await client.get("/api/v1/organizations/external-identities/me", headers=headers_a1)
                assert res.status_code == 200
                identities = res.json()["identities"]
                slack_identity = next((i for i in identities if i["provider"] == "slack"), None)
                assert slack_identity is not None, "Expected a real auto-created Slack identity"
                assert slack_identity["external_account_id"] == SLACK_EXTERNAL_USER_ID
                assert slack_identity["verified_via_oauth"] is True
                assert set(slack_identity.keys()) == {"id", "provider", "external_account_id", "external_display_name", "verified_via_oauth"}, \
                    f"Response must never include credential fields: {slack_identity.keys()}"
                identity_id = slack_identity["id"]
                print(f"SUCCESS: Real ExternalIdentity auto-created for user 1, external_account_id={SLACK_EXTERNAL_USER_ID}.")

                # 2. Integration.external_workspace_id/name captured from the same response.
                print("\nTest 2: Verifying Integration workspace metadata was captured...")
                async with SessionLocal() as session:
                    int_res = await session.execute(select(Integration).where(Integration.organization_id == org_a_id, Integration.provider == "slack"))
                    integration = int_res.scalar_one()
                    assert integration.external_workspace_id == SLACK_TEAM_ID
                    assert integration.external_workspace_name == SLACK_TEAM_NAME
                print("SUCCESS: Integration.external_workspace_id/name correctly captured.")

                # 3. Re-connecting the SAME user updates the existing row rather than duplicating.
                print("\nTest 3: Verifying re-connecting Slack refreshes rather than duplicates...")
                res = await client.get("/api/v1/integrations/oauth/slack/callback?code=fake_code_2", headers=headers_a1)
                assert res.status_code == 200
                async with SessionLocal() as session:
                    res_db = await session.execute(select(ExternalIdentity).where(
                        ExternalIdentity.organization_id == org_a_id, ExternalIdentity.provider == "slack", ExternalIdentity.is_active == True
                    ))
                    rows = res_db.scalars().all()
                    assert len(rows) == 1, f"Expected exactly 1 active identity after re-connect, got {len(rows)}"
                print("SUCCESS: Re-connecting did not create a duplicate identity row.")

                # 4. THE CRITICAL CHECK: a second Org A user authenticating as the SAME Slack
                # account must NOT get linked to it (would silently reassign the identity) --
                # but the OAuth connection itself still succeeds.
                print("\nTest 4: Verifying a conflicting identity link is skipped without breaking the OAuth connection...")
                res = await client.get("/api/v1/integrations/oauth/slack/callback?code=fake_code_3", headers=headers_a2)
                assert res.status_code == 200, f"OAuth connect itself must still succeed: {res.text}"

                res = await client.get("/api/v1/organizations/external-identities/me", headers=headers_a2)
                assert res.status_code == 200
                assert not any(i["provider"] == "slack" for i in res.json()["identities"]), \
                    "User 2 must NOT have been linked to User 1's already-claimed Slack account"

                async with SessionLocal() as session:
                    owner = await session.get(ExternalIdentity, uuid.UUID(identity_id))
                    a1_user_id = (await client.get("/api/v1/users/me", headers=headers_a1)).json()["id"]
                    assert str(owner.user_id) == a1_user_id, "Original identity owner must be unchanged"
                print("SUCCESS: Conflicting external account correctly refused a second link; original mapping unchanged.")

            # 5. Cross-tenant isolation: Org B cannot see or unlink Org A's identity.
            print("\nTest 5: Verifying cross-tenant isolation on external identities...")
            res = await client.get("/api/v1/organizations/external-identities/me", headers=headers_b)
            assert res.status_code == 200
            assert res.json()["identities"] == [], "Org B's own identity list must be empty (never Org A's)"

            res = await client.delete(f"/api/v1/organizations/external-identities/{identity_id}", headers=headers_b)
            assert res.status_code == 404, f"Expected 404 for cross-tenant unlink, got {res.status_code}: {res.text}"
            async with SessionLocal() as session:
                still_active = await session.get(ExternalIdentity, uuid.UUID(identity_id))
                assert still_active.is_active is True, "Org B's rejected unlink attempt must not have changed Org A's identity"
            print("SUCCESS: Cross-tenant identity access correctly rejected (404); state unchanged.")

            # 6. A non-owner, non-admin Org A user cannot unlink someone else's identity.
            print("\nTest 6: Verifying a non-owner, non-admin cannot unlink another user's identity...")
            res = await client.delete(f"/api/v1/organizations/external-identities/{identity_id}", headers=headers_a2)
            assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
            print("SUCCESS: Non-owner, non-admin correctly denied (403).")

            # 7. An OrgAdmin CAN unlink another user's identity (admin override).
            print("\nTest 7: Verifying OrgAdmin can unlink another user's identity...")
            res = await client.delete(f"/api/v1/organizations/external-identities/{identity_id}", headers=headers_admin)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            assert res.json()["status"] == "unlinked"

            res = await client.get("/api/v1/organizations/external-identities/me", headers=headers_a1)
            assert not any(i["id"] == identity_id for i in res.json()["identities"]), "Unlinked identity must no longer appear"
            print("SUCCESS: OrgAdmin unlinked the identity; it no longer appears for its former owner.")

            # 8. An unknown identity_id returns 404, not a crash.
            print("\nTest 8: Verifying an unknown identity_id returns 404...")
            res = await client.delete(f"/api/v1/organizations/external-identities/{uuid.uuid4()}", headers=headers_admin)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Unknown identity_id correctly returns 404.")

            # 9. Audit log contains only safe identity-management information.
            print("\nTest 9: Verifying audit log entries are safe and complete...")
            async with SessionLocal() as session:
                link_res = await session.execute(select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "external_identity:link"))
                link_rows = link_res.scalars().all()
                assert len(link_rows) >= 1
                for row in link_rows:
                    assert "token" not in str(row.details).lower(), "Audit details must never mention tokens"
                    assert row.details.get("external_account_id") == SLACK_EXTERNAL_USER_ID

                unlink_res = await session.execute(select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "external_identity:unlink"))
                assert len(unlink_res.scalars().all()) >= 1
            print("SUCCESS: Audit trail present and free of credential material.")

        finally:
            print("\nCleaning up external identity test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    for model in [ExternalIdentity, OAuthToken]:
                        res_db = await session.execute(select(model).where(model.organization_id == oid))
                        for row in res_db.scalars().all():
                            await session.delete(row)
                    await session.commit()

                    int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                    for i in int_res.scalars().all():
                        await session.delete(i)
                    audit_res = await session.execute(select(AuditLog).where(AuditLog.organization_id == oid))
                    for a in audit_res.scalars().all():
                        await session.delete(a)
                    await session.commit()

                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()

                    org_row = await session.get(Organization, oid)
                    if org_row:
                        await session.delete(org_row)
                await session.commit()

            settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET = original_creds
            print("Cleanup completed.")

    print("\nAll External Identity Foundation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_external_identity_flow())
