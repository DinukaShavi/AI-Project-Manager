import asyncio
import json
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization
from app.models.event import Event
from app.integrations.github import GitHubConnector
from app.integrations.slack import SlackConnector
from app.services.integration import IntegrationService
from app.db.session import SessionLocal

async def test_integration_layer_flow():
    print("Initializing Integration Layer validation tests...")

    # 1. Test Signature Verification Utilities
    print("\nTest 1: Testing HMAC signature verification algorithms...")
    gh = GitHubConnector()
    secret = "my_webhook_secret_123"
    body = b'{"action": "opened", "issue": {"number": 42}}'
    
    # Compute valid signature
    import hmac, hashlib
    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    
    assert gh.verify_webhook_signature(body, valid_sig, secret) is True
    assert gh.verify_webhook_signature(body, "sha256=invalid_hash", secret) is False
    print("SUCCESS: GitHub HMAC SHA-256 verification verified.")

    slack = SlackConnector()
    slack_sig = "v0=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert slack.verify_webhook_signature(body, slack_sig, secret) is True
    print("SUCCESS: Slack HMAC SHA-256 verification verified.")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    created_event_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization
            async with SessionLocal() as session:
                print("\nInserting test organization database entry...")
                org = Organization(name=f"Integration Test Org {suffix}", domain=f"integ-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            # 2. Test Integration Service Webhook Ingestion Directly
            print("\nTest 2: Testing IntegrationService direct webhook ingestion...")
            async with SessionLocal() as session:
                service = IntegrationService(session)
                gh_payload = {
                    "action": "opened",
                    "pull_request": {"number": 101, "title": "Add Auth Module"},
                    "repository": {"full_name": "acme/ai-tpm"},
                    "sender": {"login": "octocat"}
                }
                gh_bytes = json.dumps(gh_payload).encode("utf-8")
                valid_gh_sig = "sha256=" + hmac.new(secret.encode("utf-8"), gh_bytes, hashlib.sha256).hexdigest()
                gh_headers = {"x-github-event": "pull_request", "x-hub-signature-256": valid_gh_sig}

                event = await service.receive_webhook(
                    provider="github",
                    payload_bytes=gh_bytes,
                    payload_json=gh_payload,
                    headers=gh_headers,
                    organization_id=test_org_id,
                    secret=secret
                )
                created_event_ids.append(event.id)
                assert event.routing_key == "github:pull_request:opened"
                assert event.processed is False
                print(f"SUCCESS: Direct GitHub webhook ingested into Outbox. Routing key: {event.routing_key}")

            # 3. Test HTTP Webhook Endpoint: POST /api/v1/integrations/github/webhook
            print("\nTest 3: Requesting POST /api/v1/integrations/github/webhook...")
            res = await client.post(
                f"/api/v1/integrations/github/webhook?organization_id={test_org_id}",
                headers={"x-github-event": "push"},
                json={"ref": "refs/heads/main", "commits": [], "repository": {"full_name": "acme/ai-tpm"}}
            )
            assert res.status_code == 202, f"Endpoint failed: {res.text}"
            res_json = res.json()
            assert res_json["status"] == "accepted"
            created_event_ids.append(uuid.UUID(res_json["event_id"]))
            print(f"SUCCESS: HTTP GitHub webhook accepted. Event ID: {res_json['event_id']}")

            # 4. Test HTTP Webhook Endpoint: POST /api/v1/integrations/slack/webhook (URL Verification)
            print("\nTest 4: Requesting POST /api/v1/integrations/slack/webhook (URL verification)...")
            res = await client.post(
                f"/api/v1/integrations/slack/webhook?organization_id={test_org_id}",
                json={"type": "url_verification", "challenge": "3eZbrw1aBcDeFgHiJkLmNoPqRsTuVwXyZ"}
            )
            assert res.status_code == 200
            assert res.text == "3eZbrw1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
            print("SUCCESS: Slack URL verification challenge answered correctly.")

            # 5. Test HTTP Webhook Endpoint: POST /api/v1/integrations/jira/webhook
            print("\nTest 5: Requesting POST /api/v1/integrations/jira/webhook...")
            jira_payload = {
                "webhookEvent": "jira:issue_created",
                "issue": {
                    "key": "TPM-42",
                    "fields": {"project": {"key": "TPM"}, "summary": "Fix login bug"}
                },
                "user": {"displayName": "Alice Smith"}
            }
            res = await client.post(
                f"/api/v1/integrations/jira/webhook?organization_id={test_org_id}",
                json=jira_payload
            )
            assert res.status_code == 202
            res_json = res.json()
            created_event_ids.append(uuid.UUID(res_json["event_id"]))
            assert res_json["routing_key"] == "jira:jira_issue_created"
            print(f"SUCCESS: Jira webhook accepted. Routing key: {res_json['routing_key']}")

        finally:
            # Cleanup test records
            print("\nCleaning up integration test database entries...")
            async with SessionLocal() as session:
                for eid in created_event_ids:
                    res = await session.execute(select(Event).where(Event.id == eid))
                    ev = res.scalar_one_or_none()
                    if ev:
                        await session.delete(ev)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Integration Layer tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_integration_layer_flow())
