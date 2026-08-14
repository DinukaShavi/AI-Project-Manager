import asyncio
import uuid
import json
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.core.security import encrypt_token
from app.models.tenant import Organization, Workspace, User, Role
from app.models.project import Project, Repository, SlackChannelMapping
from app.models.integration import Integration, OAuthToken
from app.models.audit import AuditLog
from app.services.integration import IntegrationService
from app.db.session import SessionLocal
from app.core.security import get_password_hash
from tests._auth_helpers import create_authenticated_headers


_real_async_client_post = httpx.AsyncClient.post

# Realistic-looking credential values -- if any of these literal strings show up in an
# AuditLog.details payload or in a serialized API response, the test fails.
_FAKE_ACCESS_TOKEN = "gho_secret_access_tok_should_never_be_audited"
_FAKE_REFRESH_TOKEN = "ghr_secret_refresh_tok_should_never_be_audited"
_FAKE_CLIENT_SECRET = "test_gh_client_secret"
_FAKE_AUTH_CODE = "secret_auth_code_should_never_be_audited"
_REVOKED_REFRESH_TOKEN = "revoked-refresh-should-never-be-audited"


async def _fake_provider_post(self, url, **kwargs):
    """Same mocking convention as test_oauth_system.py / test_oauth_token_refresh.py --
    intercepts only the real provider token endpoints, everything else (including this
    test's own ASGI calls) falls through to the real implementation."""
    fake_request = httpx.Request("POST", str(url))
    url_str = str(url)

    if "github.com/login/oauth/access_token" in url_str:
        data = kwargs.get("data", {})
        if data.get("grant_type") == "refresh_token":
            if data.get("refresh_token") == _REVOKED_REFRESH_TOKEN:
                # GitHub's real token endpoint returns HTTP 200 with an "error" field on
                # failure (not an HTTP error status) -- matching _refresh_token_with_provider's
                # actual GitHub branch, which calls raise_for_status() then checks "error" in data.
                return httpx.Response(200, request=fake_request, json={"error": "bad_refresh_token", "error_description": "The refresh token passed is incorrect or expired."})
            return httpx.Response(200, request=fake_request, json={"access_token": "new-access-after-refresh", "expires_in": 28800})
        assert data.get("code") == _FAKE_AUTH_CODE
        return httpx.Response(200, request=fake_request, json={
            "access_token": _FAKE_ACCESS_TOKEN, "refresh_token": _FAKE_REFRESH_TOKEN,
            "token_type": "bearer", "scope": "repo,user",
        })
    return await _real_async_client_post(self, url, **kwargs)


async def test_integration_audit_logging_flow():
    print("Initializing IntegrationService Audit Logging validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    password = "AuditIntegPass123!"
    admin_a_email = f"audit-integ-admin-a-{suffix}@example.com"
    admin_b_email = f"audit-integ-admin-b-{suffix}@example.com"

    original_creds = (settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET)
    settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET = "test_gh_client_id", _FAKE_CLIENT_SECRET

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            with patch.object(httpx.AsyncClient, "post", new=_fake_provider_post):
                async with SessionLocal() as session:
                    org_a = Organization(name=f"AuditInteg Org A {suffix}", domain=f"auditinteg-a-{suffix}.com")
                    org_b = Organization(name=f"AuditInteg Org B {suffix}", domain=f"auditinteg-b-{suffix}.com")
                    session.add_all([org_a, org_b])
                    await session.flush()
                    org_a_id, org_b_id = org_a.id, org_b.id

                    org_admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                    admin_a = User(organization_id=org_a_id, email=admin_a_email, full_name="Audit Integ Admin A", hashed_password=get_password_hash(password))
                    admin_a.roles.append(org_admin_role)
                    admin_b = User(organization_id=org_b_id, email=admin_b_email, full_name="Audit Integ Admin B", hashed_password=get_password_hash(password))
                    admin_b.roles.append(org_admin_role)
                    session.add_all([admin_a, admin_b])
                    await session.commit()
                    actor_id = admin_a.id

                    workspace_a = Workspace(organization_id=org_a_id, name="AuditInteg Workspace A")
                    session.add(workspace_a)
                    await session.flush()
                    project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="AuditInteg Project A")
                    session.add(project_a)
                    await session.commit()
                    project_a_id = project_a.id

                print(f"Test orgs/admins/project created. Org A={org_a_id} Org B={org_b_id} Project A={project_a_id}")

                # 1. OAuth grant creates the expected audit event.
                print("\nTest 1: Verifying OAuth grant (exchange_code_for_token) creates an 'oauth:connect' audit event...")
                async with SessionLocal() as session:
                    service = IntegrationService(session)
                    res = await service.exchange_code_for_token(
                        provider="github",
                        code=_FAKE_AUTH_CODE,
                        organization_id=org_a_id,
                        redirect_uri="http://localhost:3000/callback",
                        user_id=actor_id,
                    )
                assert res["status"] == "connected", "OAuth grant must still functionally succeed"
                async with SessionLocal() as session:
                    res_db = await session.execute(select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "oauth:connect"))
                    connect_logs = res_db.scalars().all()
                assert len(connect_logs) == 1
                assert connect_logs[0].organization_id == org_a_id
                assert connect_logs[0].user_id == actor_id
                assert connect_logs[0].details.get("provider") == "github"
                print("SUCCESS: 'oauth:connect' audit event recorded with correct organization/actor/provider.")

                # 2. Repository linking creates the expected audit event.
                print("\nTest 2: Verifying repository linking creates a 'repository:link' audit event...")
                async with SessionLocal() as session:
                    service = IntegrationService(session)
                    repo = await service.link_github_repository(
                        organization_id=org_a_id,
                        project_id=project_a_id,
                        external_repo_id="12345",
                        name="acme/ai-tpm",
                        clone_url=f"https://x-access-token:{_FAKE_ACCESS_TOKEN}@github.com/acme/ai-tpm.git",
                        user_id=actor_id,
                    )
                assert repo.name == "acme/ai-tpm"
                async with SessionLocal() as session:
                    res_db = await session.execute(select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "repository:link"))
                    link_logs = res_db.scalars().all()
                assert len(link_logs) == 1
                assert link_logs[0].details.get("external_repo_id") == "12345"
                assert "clone_url" not in link_logs[0].details, "clone_url can embed a credential and must never be audited"
                print("SUCCESS: 'repository:link' audit event recorded without leaking the credential-bearing clone_url.")

                # 3. Slack channel mapping creates the expected audit event.
                print("\nTest 3: Verifying Slack channel mapping creates a 'slack:channel_map' audit event...")
                async with SessionLocal() as session:
                    service = IntegrationService(session)
                    mapping = await service.map_slack_channel_to_project(
                        organization_id=org_a_id,
                        project_id=project_a_id,
                        slack_channel_id="C0123456789",
                        user_id=actor_id,
                    )
                assert mapping.slack_channel_id == "C0123456789"
                async with SessionLocal() as session:
                    res_db = await session.execute(select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "slack:channel_map"))
                    map_logs = res_db.scalars().all()
                assert len(map_logs) == 1
                assert map_logs[0].details.get("slack_channel_id") == "C0123456789"
                print("SUCCESS: 'slack:channel_map' audit event recorded correctly.")

                # 4. OAuth refresh failure / reauthorization-required creates the expected
                # audit event, without leaking the revoked refresh token value.
                print("\nTest 4: Verifying OAuth refresh failure creates an 'oauth:reauth_required' audit event...")
                async with SessionLocal() as session:
                    integration_gh = (await session.execute(
                        select(Integration).where(Integration.organization_id == org_a_id, Integration.provider == "github")
                    )).scalar_one()
                    token_rec = (await session.execute(
                        select(OAuthToken).where(OAuthToken.integration_id == integration_gh.id)
                    )).scalar_one()
                    token_rec.encrypted_refresh_token = encrypt_token(_REVOKED_REFRESH_TOKEN)
                    token_rec.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
                    await session.commit()

                    raised = False
                    try:
                        await IntegrationService(session).get_valid_oauth_token(org_a_id, "github")
                    except PermissionError:
                        raised = True
                assert raised, "Expected PermissionError for a rejected refresh"
                async with SessionLocal() as session:
                    res_db = await session.execute(select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "oauth:reauth_required"))
                    reauth_logs = res_db.scalars().all()
                assert len(reauth_logs) == 1
                assert reauth_logs[0].details.get("provider") == "github"
                assert _REVOKED_REFRESH_TOKEN not in json.dumps(reauth_logs[0].details)
                print("SUCCESS: 'oauth:reauth_required' audit event recorded without leaking the revoked refresh token.")

                # 5. OAuth revoke/disconnect creates the expected audit event.
                print("\nTest 5: Verifying OAuth revoke creates an 'oauth:disconnect' audit event...")
                async with SessionLocal() as session:
                    service = IntegrationService(session)
                    revoked = await service.revoke_oauth_token(organization_id=org_a_id, provider="github", user_id=actor_id)
                assert revoked is True
                async with SessionLocal() as session:
                    res_db = await session.execute(select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "oauth:disconnect"))
                    disconnect_logs = res_db.scalars().all()
                assert len(disconnect_logs) == 1
                print("SUCCESS: 'oauth:disconnect' audit event recorded correctly.")

                # 6-10. No credential material anywhere in ANY of this test's audit records.
                print("\nTest 6: Verifying NO credential material appears in any audit record from this flow...")
                async with SessionLocal() as session:
                    res_db = await session.execute(select(AuditLog).where(AuditLog.organization_id == org_a_id))
                    all_logs = res_db.scalars().all()
                serialized = json.dumps([{"action": l.action, "details": l.details} for l in all_logs])
                for secret in [_FAKE_ACCESS_TOKEN, _FAKE_REFRESH_TOKEN, _FAKE_CLIENT_SECRET, _FAKE_AUTH_CODE, _REVOKED_REFRESH_TOKEN, "new-access-after-refresh"]:
                    assert secret not in serialized, f"Credential material '{secret}' leaked into an audit record"
                print(f"SUCCESS: All {len(all_logs)} audit records from this flow contain zero credential material.")

                # 11. Cross-tenant isolation: Org B's OrgAdmin cannot see any of Org A's
                # integration audit records through the real audit-log retrieval endpoint.
                print("\nTest 11: Verifying Org B cannot see Org A's integration audit records...")
                res = await client.post("/api/v1/auth/login", json={"email": admin_b_email, "password": password})
                assert res.status_code == 200
                headers_b = {"Authorization": f"Bearer {res.json()['access_token']}"}

                res = await client.get("/api/v1/audit-logs", headers=headers_b)
                assert res.status_code == 200, res.text
                b_actions = {e["action"] for e in res.json()["entries"]}
                assert "oauth:connect" not in b_actions
                assert "oauth:disconnect" not in b_actions
                assert "repository:link" not in b_actions
                assert "slack:channel_map" not in b_actions
                assert "oauth:reauth_required" not in b_actions
                raw_text = res.text
                for secret in [_FAKE_ACCESS_TOKEN, _FAKE_REFRESH_TOKEN, _FAKE_CLIENT_SECRET]:
                    assert secret not in raw_text
                print("SUCCESS: Org B sees none of Org A's integration audit records or credential material.")

                # 12. Org A's own admin CAN see its own integration audit trail (regression
                # guard -- the fix must not break legitimate same-tenant visibility).
                print("\nTest 12: Verifying Org A's own admin can see its own integration audit trail...")
                res = await client.post("/api/v1/auth/login", json={"email": admin_a_email, "password": password})
                assert res.status_code == 200
                headers_a = {"Authorization": f"Bearer {res.json()['access_token']}"}
                res = await client.get("/api/v1/audit-logs", headers=headers_a)
                assert res.status_code == 200
                a_actions = {e["action"] for e in res.json()["entries"]}
                assert {"oauth:connect", "repository:link", "slack:channel_map", "oauth:reauth_required", "oauth:disconnect"}.issubset(a_actions)
                print("SUCCESS: Org A's admin retains full visibility into its own integration audit trail.")

        finally:
            (settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET) = original_creds
            print("\nCleaning up integration audit logging test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    for model in [AuditLog, SlackChannelMapping, Repository]:
                        res_m = await session.execute(select(model).where(model.organization_id == oid))
                        for row in res_m.scalars().all():
                            await session.delete(row)
                    await session.commit()

                    tok_res = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == oid))
                    for t in tok_res.scalars().all():
                        await session.delete(t)
                    int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                    for i in int_res.scalars().all():
                        await session.delete(i)
                    proj_res = await session.execute(select(Project).where(Project.organization_id == oid))
                    for p in proj_res.scalars().all():
                        await session.delete(p)
                    ws_res = await session.execute(select(Workspace).where(Workspace.organization_id == oid))
                    for w in ws_res.scalars().all():
                        await session.delete(w)
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

    print("\nAll IntegrationService Audit Logging tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_integration_audit_logging_flow())
