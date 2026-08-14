import asyncio
import uuid
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from loguru import logger
from sqlalchemy import select

import app.db.base # Register models
from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.core.distributed_lock import get_lock_manager
from app.models.tenant import Organization
from app.models.integration import Integration, OAuthToken
from app.services.integration import IntegrationService
from app.db.session import SessionLocal


_real_async_client_post = httpx.AsyncClient.post

refresh_call_log = []


async def _fake_provider_refresh_post(self, url, **kwargs):
    """Stand-in for real provider token endpoints (per engineering_handbook.md's testing
    pyramid: unit tests mock externals) -- exercises OUR request construction/response
    parsing for the refresh_token grant, not a real Google/GitHub/Atlassian server.
    Patched at the class level, so anything that isn't one of these provider endpoints
    must fall through to the real implementation (this also intercepts this test's own
    local ASGI calls, of which this file makes none via httpx directly)."""
    fake_request = httpx.Request("POST", str(url))
    url_str = str(url)

    if "oauth2.googleapis.com/token" in url_str:
        refresh_call_log.append(("google", kwargs["data"].get("refresh_token")))
        if kwargs["data"].get("refresh_token") == "revoked-google-refresh":
            return httpx.Response(400, request=fake_request, json={"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
        return httpx.Response(200, request=fake_request, json={
            "access_token": "new-google-access-token", "expires_in": 3600, "scope": "calendar.events",
            # Google's normal behavior: no new refresh_token on refresh.
        })

    if "github.com/login/oauth/access_token" in url_str:
        refresh_call_log.append(("github", kwargs["data"].get("refresh_token")))
        return httpx.Response(200, request=fake_request, json={
            "access_token": "new-github-access-token", "expires_in": 28800,
            "refresh_token": "new-github-refresh-token", "refresh_token_expires_in": 15897600,
        })

    if "auth.atlassian.com/oauth/token" in url_str:
        refresh_call_log.append(("jira", kwargs["json"].get("refresh_token")))
        return httpx.Response(200, request=fake_request, json={
            "access_token": "new-jira-access-token", "expires_in": 3600,
            "refresh_token": "new-jira-refresh-token",
        })

    return await _real_async_client_post(self, url, **kwargs)


async def _make_integration(session, provider, access_token="old-access-token", refresh_token="old-refresh-token", expires_at=None, org=None):
    if org is None:
        org = Organization(name=f"OAuth Refresh Test Org {uuid.uuid4().hex[:8]}", domain=f"{uuid.uuid4().hex[:8]}.example.com")
        session.add(org)
        await session.flush()

    integration = Integration(organization_id=org.id, provider=provider, is_active=True)
    session.add(integration)
    await session.flush()

    token_rec = OAuthToken(
        organization_id=org.id,
        integration_id=integration.id,
        encrypted_access_token=encrypt_token(access_token),
        encrypted_refresh_token=encrypt_token(refresh_token) if refresh_token else "",
        expires_at=expires_at,
    )
    session.add(token_rec)
    await session.commit()
    return org, integration, token_rec


async def test_oauth_token_refresh_flow():
    print("Initializing Third-Party OAuth Token Refresh validation tests...")

    org_ids = []
    original_creds = (
        settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET,
        settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET,
        settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET,
    )
    settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET = "test_gh_client_id", "test_gh_client_secret"
    settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET = "test_jira_client_id", "test_jira_client_secret"
    settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET = "test_google_client_id", "test_google_client_secret"

    try:
        with patch.object(httpx.AsyncClient, "post", new=_fake_provider_refresh_post):
            # 1. A still-valid (non-expired) access token is returned as-is, with NO
            # refresh call made at all.
            print("\nTest 1: Verifying a valid access token is returned without triggering a refresh...")
            refresh_call_log.clear()
            async with SessionLocal() as session:
                org1, integration1, token1 = await _make_integration(
                    session, "google_calendar", access_token="still-valid-token",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
                )
                org_ids.append(org1.id)
                token = await IntegrationService(session).get_valid_oauth_token(org1.id, "google_calendar")
            assert token == "still-valid-token"
            assert len(refresh_call_log) == 0, "No refresh call should have been made for a valid token"
            print("SUCCESS: Valid token returned directly; no provider call made.")

            # 2. An expired Google Calendar token refreshes successfully and returns the
            # NEW access token, not the stale one.
            print("\nTest 2: Verifying an expired Google token refreshes successfully...")
            refresh_call_log.clear()
            async with SessionLocal() as session:
                org2, integration2, token2 = await _make_integration(
                    session, "google_calendar", access_token="expired-google-token", refresh_token="valid-google-refresh",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org2.id)
                new_token = await IntegrationService(session).get_valid_oauth_token(org2.id, "google_calendar")
            assert new_token == "new-google-access-token"
            assert refresh_call_log == [("google", "valid-google-refresh")]
            print("SUCCESS: Expired Google token refreshed; new access token returned.")

            # 3. The new access token is encrypted before persistence -- the raw DB column
            # must never contain the plaintext value.
            print("\nTest 3: Verifying the new access token is encrypted at rest...")
            async with SessionLocal() as session:
                refreshed_rec = await session.get(OAuthToken, token2.id)
                assert refreshed_rec.encrypted_access_token != "new-google-access-token"
                assert decrypt_token(refreshed_rec.encrypted_access_token) == "new-google-access-token"
                assert refreshed_rec.expires_at > datetime.now(timezone.utc)
            print("SUCCESS: New access token stored encrypted; decrypts to the correct value.")

            # 4/6. Google does not return a new refresh_token -- the EXISTING encrypted
            # refresh token must be preserved untouched, not wiped or replaced with junk.
            print("\nTest 4: Verifying the existing refresh token is preserved when the provider doesn't rotate it...")
            async with SessionLocal() as session:
                refreshed_rec = await session.get(OAuthToken, token2.id)
                assert decrypt_token(refreshed_rec.encrypted_refresh_token) == "valid-google-refresh"
                assert refreshed_rec.encrypted_refresh_token != "valid-google-refresh"  # still encrypted
            print("SUCCESS: Existing (unrotated) refresh token correctly preserved, still encrypted.")

            # 5. A provider that DOES return a new refresh token (GitHub, Jira) correctly
            # rotates the stored encrypted refresh token to the new value.
            print("\nTest 5: Verifying refresh-token rotation for providers that reissue one (GitHub, Jira)...")
            async with SessionLocal() as session:
                org3, integration3, token3 = await _make_integration(
                    session, "github", access_token="expired-gh-token", refresh_token="old-github-refresh",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org3.id)
                new_gh_token = await IntegrationService(session).get_valid_oauth_token(org3.id, "github")
            assert new_gh_token == "new-github-access-token"
            async with SessionLocal() as session:
                refreshed_gh = await session.get(OAuthToken, token3.id)
                assert decrypt_token(refreshed_gh.encrypted_refresh_token) == "new-github-refresh-token", "GitHub's rotated refresh token must replace the old one"

                org4, integration4, token4 = await _make_integration(
                    session, "jira", access_token="expired-jira-token", refresh_token="old-jira-refresh",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org4.id)
                new_jira_token = await IntegrationService(session).get_valid_oauth_token(org4.id, "jira")
            assert new_jira_token == "new-jira-access-token"
            async with SessionLocal() as session:
                refreshed_jira = await session.get(OAuthToken, token4.id)
                assert decrypt_token(refreshed_jira.encrypted_refresh_token) == "new-jira-refresh-token"
            print("SUCCESS: GitHub and Jira refresh-token rotation correctly persisted.")

            # 7. A revoked/invalid refresh token produces a clear, distinct authentication
            # failure (PermissionError), not a crash or a silently-returned stale token.
            print("\nTest 7: Verifying a revoked refresh token raises a clear authentication failure...")
            async with SessionLocal() as session:
                org5, integration5, token5 = await _make_integration(
                    session, "google_calendar", access_token="expired-revoked-token", refresh_token="revoked-google-refresh",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org5.id)
                raised = False
                try:
                    await IntegrationService(session).get_valid_oauth_token(org5.id, "google_calendar")
                except PermissionError as e:
                    raised = True
                    assert "revoked-google-refresh" not in str(e), "Raw refresh token must never appear in an error message"
            assert raised, "Expected PermissionError for a revoked refresh token"
            async with SessionLocal() as session:
                unchanged = await session.get(OAuthToken, token5.id)
                assert decrypt_token(unchanged.encrypted_access_token) == "expired-revoked-token", "The stale token must not be silently kept as if valid, nor corrupted"
            print("SUCCESS: Revoked refresh token correctly raised PermissionError without leaking the token value.")

            # 8. A missing refresh token (never issued) is handled correctly -- PermissionError,
            # and no provider call is attempted at all.
            print("\nTest 8: Verifying a missing refresh token is handled without attempting a provider call...")
            refresh_call_log.clear()
            async with SessionLocal() as session:
                org6, integration6, token6 = await _make_integration(
                    session, "github", access_token="expired-no-refresh-token", refresh_token=None,
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org6.id)
                raised = False
                try:
                    await IntegrationService(session).get_valid_oauth_token(org6.id, "github")
                except PermissionError:
                    raised = True
            assert raised, "Expected PermissionError when no refresh token is stored"
            assert len(refresh_call_log) == 0, "No provider call should be attempted without a refresh token"
            print("SUCCESS: Missing refresh token correctly handled with no provider call attempted.")

            # 9. Slack: this codebase's OAuth exchange never captures a refresh_token under
            # Slack's standard (non-rotation) app model, so a Slack integration behaves
            # exactly like the "missing refresh token" case above -- verified explicitly.
            print("\nTest 9: Verifying Slack (no refresh-token support in this OAuth model) is handled correctly...")
            async with SessionLocal() as session:
                org7, integration7, token7 = await _make_integration(
                    session, "slack", access_token="expired-slack-token", refresh_token=None,
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org7.id)
                raised = False
                try:
                    await IntegrationService(session).get_valid_oauth_token(org7.id, "slack")
                except PermissionError:
                    raised = True
            assert raised, "Expected PermissionError for Slack (no refresh token available under this app's OAuth model)"
            print("SUCCESS: Slack correctly falls back to 'no refresh token available' rather than a fabricated refresh flow.")

            # 11. Two concurrent callers discovering the same expired token must not both hit
            # the provider -- the distributed lock serializes them, and the second caller
            # sees the already-refreshed token instead of racing/rotating twice.
            print("\nTest 11: Verifying concurrent refresh attempts are serialized by the distributed lock...")
            refresh_call_log.clear()
            async with SessionLocal() as session:
                org8, integration8, token8 = await _make_integration(
                    session, "google_calendar", access_token="expired-concurrent-token", refresh_token="concurrent-google-refresh",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org8.id)
                await session.commit()

            async def _resolve():
                async with SessionLocal() as s:
                    return await IntegrationService(s).get_valid_oauth_token(org8.id, "google_calendar")

            results = await asyncio.gather(_resolve(), _resolve())
            assert all(r == "new-google-access-token" for r in results), f"Both concurrent callers must see the refreshed token, got {results}"
            google_calls = [c for c in refresh_call_log if c[0] == "google"]
            assert len(google_calls) == 1, f"Expected exactly ONE provider refresh call across both concurrent callers, got {len(google_calls)}"
            print("SUCCESS: Concurrent refresh attempts correctly serialized; provider called exactly once.")

            # 12. Tenant isolation: Org A's token must never be returned when resolving for
            # a DIFFERENT organization, even for the same provider.
            print("\nTest 12: Verifying tenant isolation between two organizations' tokens...")
            async with SessionLocal() as session:
                org9, integration9, token9 = await _make_integration(
                    session, "github", access_token="org9-github-token",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
                )
                org_ids.append(org9.id)
                other_org_id = uuid.uuid4()
                cross_result = await IntegrationService(session).get_valid_oauth_token(other_org_id, "github")
            assert cross_result is None, "A random/other organization must never resolve to another org's token"
            print("SUCCESS: Tenant isolation verified; an unrelated organization resolves to no token.")

            # 13. Calendar synchronization automatically benefits from refresh -- calling
            # sync_calendar_events (the exact logic behind both the manual endpoint and the
            # poller) with an expired-but-refreshable token must succeed transparently.
            print("\nTest 13: Verifying Calendar sync automatically benefits from transparent token refresh...")
            from app.models.tenant import Workspace
            from app.models.project import Project

            async def fake_calendar_events(self, url, **kwargs):
                return httpx.Response(200, request=httpx.Request("GET", str(url)), json={"items": []})

            async with SessionLocal() as session:
                org10, integration10, token10 = await _make_integration(
                    session, "google_calendar", access_token="expired-calsync-token", refresh_token="calsync-google-refresh",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org10.id)
                workspace10 = Workspace(organization_id=org10.id, name="Refresh Test Workspace")
                session.add(workspace10)
                await session.flush()
                project10 = Project(organization_id=org10.id, workspace_id=workspace10.id, name="Refresh Test Project")
                session.add(project10)
                await session.commit()

                with patch.object(httpx.AsyncClient, "get", new=fake_calendar_events):
                    result = await IntegrationService(session).sync_calendar_events(
                        organization_id=org10.id, project_id=project10.id,
                        start_date=datetime.now(timezone.utc), end_date=datetime.now(timezone.utc) + timedelta(days=1),
                    )
            assert result["events_synced"] == 0  # no events in this fake page, but no PermissionError raised
            print("SUCCESS: sync_calendar_events transparently refreshed the expired token and completed successfully.")

            # 16. No plaintext access/refresh tokens ever appear in logs during a refresh.
            print("\nTest 16: Verifying no plaintext token values leak into logs during a refresh...")
            log_lines = []
            sink_id = logger.add(lambda msg: log_lines.append(str(msg)), level="DEBUG")
            async with SessionLocal() as session:
                org11, integration11, token11 = await _make_integration(
                    session, "google_calendar", access_token="expired-logcheck-token", refresh_token="super-secret-refresh-value",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
                )
                org_ids.append(org11.id)
                await IntegrationService(session).get_valid_oauth_token(org11.id, "google_calendar")
            logger.remove(sink_id)
            full_log = "\n".join(log_lines)
            assert "super-secret-refresh-value" not in full_log
            assert "new-google-access-token" not in full_log
            assert "expired-logcheck-token" not in full_log
            print("SUCCESS: No plaintext credential material appeared in logs during token refresh.")

    finally:
        (settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET,
         settings.JIRA_CLIENT_ID, settings.JIRA_CLIENT_SECRET,
         settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET) = original_creds

        # Release any lock left held if a test failed mid-way, so it doesn't poison later runs.
        lock_manager = get_lock_manager()
        for oid in org_ids:
            try:
                tok = await lock_manager.acquire_lock(f"oauth_refresh:{oid}:google_calendar", ttl_seconds=1)
                if tok:
                    await lock_manager.release_lock(f"oauth_refresh:{oid}:google_calendar", tok)
            except Exception:
                pass

        print("\nCleaning up OAuth token refresh test database entries...")
        async with SessionLocal() as session:
            from app.models.project import Project
            from app.models.tenant import Workspace
            for oid in org_ids:
                proj_res = await session.execute(select(Project).where(Project.organization_id == oid))
                for p in proj_res.scalars().all():
                    await session.delete(p)
                ws_res = await session.execute(select(Workspace).where(Workspace.organization_id == oid))
                for w in ws_res.scalars().all():
                    await session.delete(w)
                await session.commit()

                tok_res = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == oid))
                for t in tok_res.scalars().all():
                    await session.delete(t)
                int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                for i in int_res.scalars().all():
                    await session.delete(i)
                await session.commit()

                org_res = await session.execute(select(Organization).where(Organization.id == oid))
                db_org = org_res.scalar_one_or_none()
                if db_org:
                    await session.delete(db_org)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Third-Party OAuth Token Refresh tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_oauth_token_refresh_flow())
