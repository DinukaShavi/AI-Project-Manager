import asyncio
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.models.tenant import Organization, User
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


def _fake_response(url, json_body):
    return httpx.Response(200, request=httpx.Request("GET", str(url)), json=json_body)


_real_async_client_get = httpx.AsyncClient.get


async def test_jira_projects_list_flow():
    print("Initializing Jira Projects List (api_contract.md 5.A) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_id = None
    original_jira = (settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)
    settings.JIRA_BASE_URL = "acme-projects-test"
    settings.JIRA_EMAIL = "bot@acme-projects-test.com"
    settings.JIRA_API_TOKEN = "jira-projects-mocked-token"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org = Organization(name=f"Jira Projects Test Org {suffix}", domain=f"jiraprojects-{suffix}.com")
                session.add(org)
                await session.commit()
                org_id = org.id
            headers = await create_authenticated_headers(client, org_id)
            print(f"Test org and user created. Org={org_id}")

            # 1. Unauthenticated requests must be rejected -- the old mock endpoint had no
            # auth check at all.
            print("\nTest 1: Verifying the endpoint requires authentication...")
            res = await client.get("/api/v1/integrations/jira/projects")
            assert res.status_code == 401, f"Expected 401 for an unauthenticated request, got {res.status_code}"
            print("SUCCESS: Unauthenticated request correctly rejected with 401.")

            # 2. Real data: the response must reflect the (mocked) Jira REST API v3's actual
            # project list, following pagination through multiple pages, not fabricated
            # constants.
            print("\nTest 2: Verifying real project data is fetched across multiple paginated pages...")
            call_count = {"n": 0}

            async def fake_jira_project_search(self, url, **kwargs):
                if "acme-projects-test.atlassian.net/rest/api/3/project/search" not in str(url):
                    return await _real_async_client_get(self, url, **kwargs)
                assert kwargs["auth"] == ("bot@acme-projects-test.com", "jira-projects-mocked-token")
                call_count["n"] += 1
                start_at = kwargs["params"]["startAt"]
                if start_at == 0:
                    return _fake_response(url, {
                        "values": [{"id": "10001", "key": "TPM", "name": "Technical Project Manager", "projectTypeKey": "software"}],
                        "isLast": False,
                    })
                elif start_at == 50:
                    return _fake_response(url, {
                        "values": [{"id": "10002", "key": "INFRA", "name": "Cloud Infrastructure", "projectTypeKey": "business"}],
                        "isLast": True,
                    })
                raise AssertionError(f"Unexpected startAt={start_at}")

            with patch.object(httpx.AsyncClient, "get", new=fake_jira_project_search):
                res = await client.get("/api/v1/integrations/jira/projects", headers=headers)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            assert call_count["n"] == 2, "Expected pagination to follow through both pages"
            body = res.json()
            print("SUCCESS: Fetched real project data across 2 paginated pages.")

            # 3. Response schema must match api_contract.md section 5.A EXACTLY:
            # {"projects": [{"key": ..., "name": ...}]} -- no extra fabricated fields.
            print("\nTest 3: Verifying the response matches the documented schema exactly...")
            assert set(body.keys()) == {"projects"}, f"Expected only a 'projects' key, got: {list(body.keys())}"
            assert body["projects"] == [
                {"key": "TPM", "name": "Technical Project Manager"},
                {"key": "INFRA", "name": "Cloud Infrastructure"},
            ]
            for p in body["projects"]:
                assert set(p.keys()) == {"key", "name"}, f"Expected only key/name fields per project, got: {p}"
            print("SUCCESS: Response matches the documented api_contract.md schema exactly.")

            # 4. No credential material (API token, email) leaks into the response.
            print("\nTest 4: Verifying no credential material appears in the response...")
            raw_text = res.text
            assert "jira-projects-mocked-token" not in raw_text
            assert "bot@acme-projects-test.com" not in raw_text
            print("SUCCESS: No credential material present in the response body.")

            # 5. A provider-side failure must be surfaced as a clean error, never fabricated
            # data pretending to be real.
            print("\nTest 5: Verifying a Jira API failure is surfaced safely, not papered over with fake data...")

            async def fake_jira_failure(self, url, **kwargs):
                if "acme-projects-test.atlassian.net/rest/api/3/project/search" not in str(url):
                    return await _real_async_client_get(self, url, **kwargs)
                return httpx.Response(500, request=httpx.Request("GET", str(url)), json={"errorMessages": ["Internal error"]})

            with patch.object(httpx.AsyncClient, "get", new=fake_jira_failure):
                res = await client.get("/api/v1/integrations/jira/projects", headers=headers)
            assert res.status_code == 502, f"Expected 502 for an upstream Jira failure, got {res.status_code}: {res.text}"
            assert "projects" not in res.json()
            print("SUCCESS: Jira API failure correctly surfaced as 502, no fabricated project data returned.")

            # 6. Missing Jira credentials must be a clear 400, not a crash or fake data.
            print("\nTest 6: Verifying missing Jira credentials produce a clean 400...")
            settings.JIRA_API_TOKEN = None
            res = await client.get("/api/v1/integrations/jira/projects", headers=headers)
            assert res.status_code == 400, f"Expected 400 for missing Jira credentials, got {res.status_code}: {res.text}"
            settings.JIRA_API_TOKEN = "jira-projects-mocked-token"
            print("SUCCESS: Missing Jira credentials correctly rejected with 400.")

        finally:
            settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = original_jira
            print("\nCleaning up Jira projects list test database entries...")
            async with SessionLocal() as session:
                if org_id:
                    user_res = await session.execute(select(User).where(User.organization_id == org_id))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()
                    org_res = await session.execute(select(Organization).where(Organization.id == org_id))
                    db_org = org_res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                    await session.commit()
            print("Cleanup completed.")

    print("\nAll Jira Projects List tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_jira_projects_list_flow())
