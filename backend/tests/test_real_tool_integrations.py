import asyncio
import uuid
import httpx
from unittest.mock import patch
from sqlalchemy import select

import app.db.base # Register models
from app.core.config import settings
from app.core.security import encrypt_token
from app.models.tenant import Organization
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from app.tools.github_tools import GitHubCreateIssueTool, GitHubGetPRDiffTool
from app.tools.jira_tools import JiraGetIssueTool, JiraUpdateIssueStatusTool
from app.tools.slack_tools import SlackPostMessageTool


def _fake_response(url, json_body=None, text_body=None, status_code=200):
    return httpx.Response(
        status_code, request=httpx.Request("GET", str(url)),
        json=json_body, text=text_body if json_body is None else None,
    )


async def _connect_integration(session, organization_id, provider: str, access_token: str) -> None:
    """Mirror the real exchange_code_for_token persistence shape (encrypted token row) so
    these tests exercise the exact same lookup path the tools use in production."""
    integration = Integration(organization_id=organization_id, provider=provider, is_active=True)
    session.add(integration)
    await session.flush()
    token_rec = OAuthToken(
        organization_id=organization_id,
        integration_id=integration.id,
        encrypted_access_token=encrypt_token(access_token),
        encrypted_refresh_token=encrypt_token(""),
        scopes=[f"{provider}:read", f"{provider}:write"],
    )
    session.add(token_rec)
    await session.commit()


async def test_real_tool_integrations_flow():
    print("Initializing Real Tool Execution (GitHub/Jira/Slack) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    original_jira = (settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)

    try:
        async with SessionLocal() as session:
            org = Organization(name=f"Real Tools Test Org {suffix}", domain=f"realtools-{suffix}.com")
            session.add(org)
            await session.flush()
            test_org_id = org.id
            await session.commit()
        print(f"Test Organization created. ID: {test_org_id}")

        # 1. GitHub create_issue: real OAuth token connected, real GitHub API mocked to succeed.
        print("\nTest 1: Verifying github_create_issue with a connected token calls the real GitHub API...")
        async with SessionLocal() as session:
            await _connect_integration(session, test_org_id, "github", "gho_real_mocked_token")

        async def fake_github_create(self, url, **kwargs):
            assert "api.github.com/repos/acme/ai-tpm/issues" in str(url)
            assert kwargs["headers"]["Authorization"] == "token gho_real_mocked_token"
            assert kwargs["json"]["title"] == "Real Tool Execution Test"
            return _fake_response(url, json_body={"number": 501, "html_url": "https://github.com/acme/ai-tpm/issues/501", "title": "Real Tool Execution Test", "body": "body text"})

        async with SessionLocal() as session:
            with patch.object(httpx.AsyncClient, "post", new=fake_github_create):
                tool = GitHubCreateIssueTool()
                result = await tool.execute(
                    {"organization_id": str(test_org_id), "repo": "acme/ai-tpm", "title": "Real Tool Execution Test", "body": "body text"},
                    session=session,
                )
        assert result["status"] == "success"
        assert result["issue_number"] == 501, f"Expected the real mocked issue number (501), not a fabricated one, got: {result}"
        assert result["url"] == "https://github.com/acme/ai-tpm/issues/501"
        print("SUCCESS: github_create_issue made a real, correctly-authenticated request and returned the real response.")

        # 2. GitHub get_pr_diff: real API mocked to succeed with real stats.
        print("\nTest 2: Verifying github_get_pr_diff returns real PR stats from the mocked API...")

        async def fake_github_get_pr(self, url, **kwargs):
            assert "api.github.com/repos/acme/ai-tpm/pulls/42" in str(url)
            return _fake_response(url, json_body={"title": "Fix auth bug", "changed_files": 7, "additions": 120, "deletions": 30})

        async with SessionLocal() as session:
            with patch.object(httpx.AsyncClient, "get", new=fake_github_get_pr):
                tool = GitHubGetPRDiffTool()
                result = await tool.execute(
                    {"organization_id": str(test_org_id), "repo": "acme/ai-tpm", "pr_number": 42},
                    session=session,
                )
        assert result["status"] == "success"
        assert result["files_changed"] == 7 and result["additions"] == 120 and result["deletions"] == 30, \
            f"Expected real mocked PR stats, not fabricated ones, got: {result}"
        print("SUCCESS: github_get_pr_diff returned real (mocked) PR statistics, not fabricated constants.")

        # 3. Slack post_message: real OAuth token connected, real Slack API mocked to succeed.
        print("\nTest 3: Verifying slack_post_message with a connected token calls the real Slack API...")
        async with SessionLocal() as session:
            await _connect_integration(session, test_org_id, "slack", "xoxb-real-mocked-token")

        async def fake_slack_post(self, url, **kwargs):
            assert "slack.com/api/chat.postMessage" in str(url)
            assert kwargs["headers"]["Authorization"] == "Bearer xoxb-real-mocked-token"
            return _fake_response(url, json_body={"ok": True, "channel": "C12345", "ts": "1721999999.000001"})

        async with SessionLocal() as session:
            with patch.object(httpx.AsyncClient, "post", new=fake_slack_post):
                tool = SlackPostMessageTool()
                result = await tool.execute(
                    {"organization_id": str(test_org_id), "channel": "#dev-alerts", "message": "Deployment complete"},
                    session=session,
                )
        assert result["status"] == "success"
        assert result["ts"] == "1721999999.000001", f"Expected the real mocked Slack timestamp, not a fabricated one, got: {result}"
        print("SUCCESS: slack_post_message made a real, correctly-authenticated request and returned the real response.")

        # 4. Jira get_issue + transition_issue: instance-wide static API token, real (mocked) API.
        print("\nTest 4: Verifying Jira tools use the real (mocked) Jira REST API v3...")
        settings.JIRA_BASE_URL = "acme-test"
        settings.JIRA_EMAIL = "bot@acme-test.com"
        settings.JIRA_API_TOKEN = "jira-real-mocked-token"

        async def fake_jira_get(self, url, **kwargs):
            if "issue/TPM-101/transitions" in str(url):
                return _fake_response(url, json_body={"transitions": [
                    {"id": "31", "name": "In Progress", "to": {"name": "In Progress"}},
                    {"id": "41", "name": "Done", "to": {"name": "Done"}},
                ]})
            if "issue/TPM-101" in str(url):
                assert kwargs["auth"] == ("bot@acme-test.com", "jira-real-mocked-token")
                return _fake_response(url, json_body={"fields": {
                    "summary": "Real mocked Jira issue summary",
                    "status": {"name": "In Progress"},
                    "assignee": {"displayName": "Real Mocked User"},
                    "priority": {"name": "Highest"},
                }})
            raise AssertionError(f"Unexpected Jira GET: {url}")

        async def fake_jira_post(self, url, **kwargs):
            assert "issue/TPM-101/transitions" in str(url)
            assert kwargs["json"] == {"transition": {"id": "41"}}
            return httpx.Response(204, request=httpx.Request("POST", str(url)))

        with patch.object(httpx.AsyncClient, "get", new=fake_jira_get), patch.object(httpx.AsyncClient, "post", new=fake_jira_post):
            get_tool = JiraGetIssueTool()
            get_result = await get_tool.execute({"issue_key": "TPM-101"})
            assert get_result["status"] == "success"
            assert get_result["summary"] == "Real mocked Jira issue summary"
            assert get_result["assignee"] == "Real Mocked User"

            update_tool = JiraUpdateIssueStatusTool()
            update_result = await update_tool.execute({"issue_key": "TPM-101", "status_name": "Done"})
            assert update_result["status"] == "success"
            assert update_result["new_status"] == "Done"
        print("SUCCESS: Jira get_issue and the two-step transition_issue flow both used the real (mocked) REST API v3.")

    finally:
        settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = original_jira

        print("\nCleaning up real tool integration test database entries...")
        async with SessionLocal() as session:
            if test_org_id:
                tok_res = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == test_org_id))
                for tok in tok_res.scalars().all():
                    await session.delete(tok)
                int_res = await session.execute(select(Integration).where(Integration.organization_id == test_org_id))
                for integ in int_res.scalars().all():
                    await session.delete(integ)
                org_res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                db_org = org_res.scalar_one_or_none()
                if db_org:
                    await session.delete(db_org)
                await session.commit()
        print("Cleanup completed.")

    print("\nAll Real Tool Execution tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_real_tool_integrations_flow())
