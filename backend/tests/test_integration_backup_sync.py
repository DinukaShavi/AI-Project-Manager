import asyncio
import uuid
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import select

import app.db.base # Register models
from app.core.config import settings
from app.models.tenant import Organization
from app.models.integration import Integration
from app.models.event import Event
from app.db.session import SessionLocal
from app.services.integration import IntegrationService


def _fake_response(url, json_body):
    return httpx.Response(200, request=httpx.Request("GET", str(url)), json=json_body)


async def test_integration_backup_sync_flow():
    print("Initializing Jira Backup Delta-Sync validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    integration_a_id = None
    integration_b_id = None
    inactive_integration_id = None
    non_jira_integration_id = None
    original_jira = (settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)
    settings.JIRA_BASE_URL = "acme-backup-test"
    settings.JIRA_EMAIL = "bot@acme-backup-test.com"
    settings.JIRA_API_TOKEN = "jira-backup-mocked-token"

    try:
        async with SessionLocal() as session:
            org_a = Organization(name=f"Backup Sync Org A {suffix}", domain=f"backup-a-{suffix}.com")
            org_b = Organization(name=f"Backup Sync Org B {suffix}", domain=f"backup-b-{suffix}.com")
            session.add_all([org_a, org_b])
            await session.flush()
            org_a_id, org_b_id = org_a.id, org_b.id

            integration_a = Integration(organization_id=org_a_id, provider="jira", is_active=True, last_synced_at=None)
            integration_b = Integration(organization_id=org_b_id, provider="jira", is_active=True, last_synced_at=datetime.now(timezone.utc) - timedelta(hours=6))
            inactive_integration = Integration(organization_id=org_a_id, provider="jira", is_active=False)
            non_jira_integration = Integration(organization_id=org_a_id, provider="github", is_active=True)
            session.add_all([integration_a, integration_b, inactive_integration, non_jira_integration])
            await session.commit()
            integration_a_id = integration_a.id
            integration_b_id = integration_b.id
            inactive_integration_id = inactive_integration.id
            non_jira_integration_id = non_jira_integration.id
        print(f"Test orgs and integrations created. A={integration_a_id} (never synced) B={integration_b_id} (synced 6h ago)")

        captured_jql = {}

        async def fake_jira_search(self, url, **kwargs):
            assert "acme-backup-test.atlassian.net/rest/api/3/search" in str(url)
            captured_jql[str(kwargs["params"]["jql"])] = True
            return _fake_response(url, {"issues": [
                {"key": "TPM-201", "fields": {"summary": "Fix outbox lag", "status": {"name": "In Progress"}, "project": {"key": "TPM"}}},
                {"key": "TPM-202", "fields": {"summary": "Backup sync coverage", "status": {"name": "Done"}, "project": {"key": "TPM"}}},
            ]})

        # 1. First-ever sync (no watermark) must use the relative "-4h" JQL fallback.
        print("\nTest 1: Verifying a never-synced integration uses the '-4h' JQL fallback...")
        async with SessionLocal() as session:
            service = IntegrationService(session)
            with patch.object(httpx.AsyncClient, "get", new=fake_jira_search):
                ingested = await service.run_backup_sync(integration_a_id)
        assert ingested == 2, f"Expected 2 ingested issues, got {ingested}"
        assert any("-4h" in jql for jql in captured_jql), f"Expected the -4h fallback JQL, got: {captured_jql}"
        print("SUCCESS: Never-synced integration correctly used the -4h relative JQL query.")

        # 2. A previously-synced integration must use the absolute last_synced_at watermark.
        print("\nTest 2: Verifying a previously-synced integration uses its last_synced_at watermark...")
        captured_jql.clear()
        async with SessionLocal() as session:
            service = IntegrationService(session)
            with patch.object(httpx.AsyncClient, "get", new=fake_jira_search):
                await service.run_backup_sync(integration_b_id)
        assert any("-4h" not in jql and "updated >=" in jql for jql in captured_jql), \
            f"Expected an absolute updated>=<timestamp> JQL derived from last_synced_at, got: {captured_jql}"
        print("SUCCESS: Previously-synced integration correctly used its stored watermark instead of the fallback window.")

        # 3. Ingested issues must land as real outbox Events, and last_synced_at must advance.
        print("\nTest 3: Verifying ingested issues become real outbox Events and the watermark advances...")
        async with SessionLocal() as session:
            events_res = await session.execute(select(Event).where(Event.organization_id == org_a_id, Event.routing_key == "jira:issue_synced"))
            events = events_res.scalars().all()
            assert len(events) == 2
            assert {e.payload["issue_key"] for e in events} == {"TPM-201", "TPM-202"}

            integration_res = await session.execute(select(Integration).where(Integration.id == integration_a_id))
            refreshed = integration_res.scalar_one()
            assert refreshed.last_synced_at is not None
        print("SUCCESS: Backup sync persisted real outbox events and advanced the sync watermark.")

        # 4. Inactive and non-Jira integrations must be skipped without error.
        print("\nTest 4: Verifying inactive and non-Jira integrations are skipped...")
        async with SessionLocal() as session:
            service = IntegrationService(session)
            with patch.object(httpx.AsyncClient, "get", new=fake_jira_search):
                skipped_inactive = await service.run_backup_sync(inactive_integration_id)
                skipped_non_jira = await service.run_backup_sync(non_jira_integration_id)
        assert skipped_inactive == 0
        assert skipped_non_jira == 0
        print("SUCCESS: Inactive and non-Jira integrations correctly skipped (0 ingested, no error).")

        # 5. run_backup_sync_all must sweep every active Jira integration across ALL
        # organizations (system-wide job, RLS-bypassed) and tolerate one integration failing
        # without aborting the sweep for the rest.
        print("\nTest 5: Verifying run_backup_sync_all sweeps all orgs and tolerates a failing integration...")
        call_count = {"n": 0}

        async def flaky_jira_search(self, url, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise httpx.ConnectError("simulated network failure")
            return await fake_jira_search(self, url, **kwargs)

        async with SessionLocal() as session:
            service = IntegrationService(session)
            with patch.object(httpx.AsyncClient, "get", new=flaky_jira_search):
                results = await service.run_backup_sync_all()
        assert str(integration_a_id) in results and str(integration_b_id) in results, \
            f"Expected both active Jira integrations (across both orgs) to be swept, got: {results}"
        assert -1 in results.values(), "Expected the simulated failure to be recorded, not silently dropped"
        assert any(v > 0 for v in results.values()), "Expected the OTHER integration to still succeed despite the first one failing"
        print(f"SUCCESS: run_backup_sync_all swept {len(results)} integrations across all organizations; one failure did not abort the rest.")

    finally:
        settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = original_jira

        print("\nCleaning up backup sync test database entries...")
        async with SessionLocal() as session:
            for oid in [o for o in [org_a_id, org_b_id] if o]:
                ev_res = await session.execute(select(Event).where(Event.organization_id == oid))
                for ev in ev_res.scalars().all():
                    await session.delete(ev)
                int_res = await session.execute(select(Integration).where(Integration.organization_id == oid))
                for integ in int_res.scalars().all():
                    await session.delete(integ)
                org_res = await session.execute(select(Organization).where(Organization.id == oid))
                db_org = org_res.scalar_one_or_none()
                if db_org:
                    await session.delete(db_org)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Jira Backup Delta-Sync tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_integration_backup_sync_flow())
