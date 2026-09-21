import asyncio
import hashlib
import hmac
import secrets
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.tenant import Organization, User, Role
from app.models.event import Event
from app.models.integration import Integration
from app.db.session import SessionLocal


async def test_webhook_security_flow():
    print("Initializing Webhook Security Hardening (Phase 60) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    created_event_ids = []
    integration_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Webhook Sec Org A {suffix}", domain=f"whsec-a-{suffix}.com")
                org_b = Organization(name=f"Webhook Sec Org B {suffix}", domain=f"whsec-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                gh_integration = Integration(organization_id=org_a_id, provider="github", is_active=True, webhook_token=secrets.token_urlsafe(32))
                slack_integration = Integration(organization_id=org_a_id, provider="slack", is_active=True, webhook_token=secrets.token_urlsafe(32))
                inactive_integration = Integration(organization_id=org_a_id, provider="jira", is_active=False, webhook_token=secrets.token_urlsafe(32))
                session.add_all([gh_integration, slack_integration, inactive_integration])
                await session.flush()
                gh_token = gh_integration.webhook_token
                slack_token = slack_integration.webhook_token
                inactive_token = inactive_integration.webhook_token
                integration_ids.extend([gh_integration.id, slack_integration.id, inactive_integration.id])

                admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                admin_password = "TestPass123!"
                admin_a_email = f"whsec-admin-a-{suffix}@example.com"
                admin_b_email = f"whsec-admin-b-{suffix}@example.com"
                admin_a = User(organization_id=org_a_id, email=admin_a_email, full_name="Org A Admin", hashed_password=get_password_hash(admin_password))
                admin_b = User(organization_id=org_b_id, email=admin_b_email, full_name="Org B Admin", hashed_password=get_password_hash(admin_password))
                admin_a.roles.append(admin_role)
                admin_b.roles.append(admin_role)
                session.add_all([admin_a, admin_b])
                await session.commit()

            login_a = await client.post("/api/v1/auth/login", json={"email": admin_a_email, "password": admin_password})
            login_b = await client.post("/api/v1/auth/login", json={"email": admin_b_email, "password": admin_password})
            assert login_a.status_code == 200 and login_b.status_code == 200
            headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
            headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

            gh_body = {"action": "opened", "issue": {"number": 1}, "repository": {"full_name": "acme/repo"}}

            # 1. A valid token attributes the event to its real owning org -- not a
            #    caller-supplied one (there's no organization_id parameter left to supply).
            print("\nTest 1: Valid per-org token correctly attributes the event to its real owner...")
            res = await client.post(f"/api/v1/webhooks/github/{gh_token}", headers={"x-github-event": "issues"}, json=gh_body)
            assert res.status_code == 202, res.text
            event_id = uuid.UUID(res.json()["event_id"])
            created_event_ids.append(event_id)
            async with SessionLocal() as session:
                ev = (await session.execute(select(Event).where(Event.id == event_id))).scalar_one()
                assert ev.organization_id == org_a_id
            print("SUCCESS: Event correctly attributed to the token's real owning organization.")

            # 2. Unknown token -> 404, no event created.
            print("\nTest 2: An unknown webhook token is rejected with 404...")
            res = await client.post(f"/api/v1/webhooks/github/{secrets.token_urlsafe(32)}", headers={"x-github-event": "issues"}, json=gh_body)
            assert res.status_code == 404, res.text
            print("SUCCESS: Unknown token correctly rejected with 404.")

            # 3. Provider-mismatched token (Org A's GitHub token against the Slack route) -> 404.
            print("\nTest 3: A token used against the wrong provider's route is rejected with 404...")
            res = await client.post(f"/api/v1/webhooks/slack/{gh_token}", json={"type": "event_callback"})
            assert res.status_code == 404, res.text
            print("SUCCESS: Provider-mismatched token correctly rejected with 404.")

            # 4. An inactive integration's token is rejected -- disconnecting must revoke the URL.
            print("\nTest 4: A disconnected (inactive) integration's token is rejected with 404...")
            res = await client.post(f"/api/v1/webhooks/jira/{inactive_token}", json={"webhookEvent": "jira:issue_created", "issue": {"key": "X-1", "fields": {}}})
            assert res.status_code == 404, res.text
            print("SUCCESS: Inactive integration's token correctly rejected.")

            # 5. Fail-CLOSED: a real secret configured server-side + missing signature -> 401,
            #    no event created. This is the actual audit finding (P4) being proven fixed.
            print("\nTest 5: Proving the fail-open bug is fixed -- configured secret + missing signature is rejected...")
            original_secret = settings.GITHUB_WEBHOOK_SECRET
            settings.GITHUB_WEBHOOK_SECRET = "a_real_configured_secret_value"
            try:
                res = await client.post(f"/api/v1/webhooks/github/{gh_token}", headers={"x-github-event": "issues"}, json=gh_body)
                assert res.status_code == 401, f"Expected 401 (fail-closed), got {res.status_code}: {res.text}"
            finally:
                settings.GITHUB_WEBHOOK_SECRET = original_secret
            print("SUCCESS: Missing signature against a configured secret is correctly rejected (fail-closed).")

            # 6. Configured secret + invalid signature -> 401.
            print("\nTest 6: A configured secret with an invalid signature is rejected...")
            settings.GITHUB_WEBHOOK_SECRET = "a_real_configured_secret_value"
            try:
                res = await client.post(
                    f"/api/v1/webhooks/github/{gh_token}",
                    headers={"x-github-event": "issues", "x-hub-signature-256": "sha256=deadbeef"},
                    json=gh_body,
                )
                assert res.status_code == 401, res.text
            finally:
                settings.GITHUB_WEBHOOK_SECRET = original_secret
            print("SUCCESS: Invalid signature against a configured secret is correctly rejected.")

            # 7. Configured secret + valid signature -> 202, accepted.
            print("\nTest 7: A configured secret with a correct signature is accepted...")
            import json as _json
            settings.GITHUB_WEBHOOK_SECRET = "a_real_configured_secret_value"
            try:
                body_bytes = _json.dumps(gh_body).encode("utf-8")
                valid_sig = "sha256=" + hmac.new(b"a_real_configured_secret_value", body_bytes, hashlib.sha256).hexdigest()
                res = await client.post(
                    f"/api/v1/webhooks/github/{gh_token}",
                    headers={"x-github-event": "issues", "x-hub-signature-256": valid_sig, "content-type": "application/json"},
                    content=body_bytes,
                )
                assert res.status_code == 202, res.text
                created_event_ids.append(uuid.UUID(res.json()["event_id"]))
            finally:
                settings.GITHUB_WEBHOOK_SECRET = original_secret
            print("SUCCESS: Valid signature against a configured secret is correctly accepted.")

            # 8. No secret configured (today's real .env state) -> still 202 via token auth alone.
            print("\nTest 8: With no secret configured, the per-org token alone still authenticates...")
            assert not settings.GITHUB_WEBHOOK_SECRET, "This check assumes no GITHUB_WEBHOOK_SECRET is configured in this environment"
            res = await client.post(f"/api/v1/webhooks/github/{gh_token}", headers={"x-github-event": "issues"}, json=gh_body)
            assert res.status_code == 202, res.text
            created_event_ids.append(uuid.UUID(res.json()["event_id"]))
            print("SUCCESS: Unconfigured-secret provider still authenticates via the per-org token.")

            # 9. GET /integrations/{provider}/webhook-url -- real URL for a connected provider.
            print("\nTest 9: Org A's admin can retrieve its own real webhook URL...")
            res = await client.get("/api/v1/integrations/github/webhook-url", headers=headers_a)
            assert res.status_code == 200, res.text
            assert res.json()["webhook_path"] == f"/api/v1/webhooks/github/{gh_token}"
            print("SUCCESS: Real webhook URL correctly returned for a connected provider.")

            # 10. GET webhook-url for an unconnected provider -> 404.
            print("\nTest 10: An unconnected provider's webhook URL request returns 404...")
            res = await client.get("/api/v1/integrations/google_calendar/webhook-url", headers=headers_a)
            assert res.status_code == 404, res.text
            print("SUCCESS: Unconnected provider correctly returns 404.")

            # 11. Cross-tenant: Org B can never retrieve Org A's webhook URL/token.
            print("\nTest 11: Org B cannot retrieve Org A's webhook URL...")
            res = await client.get("/api/v1/integrations/github/webhook-url", headers=headers_b)
            assert res.status_code == 404, res.text
            print("SUCCESS: Org B correctly cannot see Org A's real webhook URL/token.")

            # 12. The old vulnerable query-param routes are gone entirely.
            print("\nTest 12: The old organization_id/secret query-param webhook routes no longer exist...")
            res = await client.post(f"/api/v1/integrations/github/webhook?organization_id={org_a_id}", json=gh_body)
            assert res.status_code == 404, f"Old vulnerable route still reachable: {res.status_code}"
            print("SUCCESS: Old client-supplied-organization_id webhook route is gone (404).")

        finally:
            print("\nCleaning up test database entries...")
            settings.GITHUB_WEBHOOK_SECRET = None
            async with SessionLocal() as session:
                for eid in created_event_ids:
                    res = await session.execute(select(Event).where(Event.id == eid))
                    ev = res.scalar_one_or_none()
                    if ev:
                        await session.delete(ev)
                await session.flush()
                for iid in integration_ids:
                    res = await session.execute(select(Integration).where(Integration.id == iid))
                    integ = res.scalar_one_or_none()
                    if integ:
                        await session.delete(integ)
                await session.flush()
                for org_id in (org_a_id, org_b_id):
                    if not org_id:
                        continue
                    res = await session.execute(select(User).where(User.organization_id == org_id))
                    for u in res.scalars().all():
                        await session.delete(u)
                await session.flush()
                for org_id in (org_a_id, org_b_id):
                    if not org_id:
                        continue
                    res = await session.execute(select(Organization).where(Organization.id == org_id))
                    org = res.scalar_one_or_none()
                    if org:
                        await session.delete(org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Webhook Security Hardening tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_webhook_security_flow())
