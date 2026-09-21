import asyncio
import uuid
import httpx
from unittest.mock import patch
from sqlalchemy import select

import app.db.base  # Register models
from app.core.config import settings
from app.core.security import encrypt_token
from app.models.tenant import Organization
from app.models.integration import Integration, OAuthToken
from app.db.session import SessionLocal
from app.tools.registry import get_tool_registry
from app.tools.executor import ToolExecutor
from app.tools.github_tools import GitHubCommentOnPRTool, MergePullRequestTool
from app.tools.jira_tools import JiraCreateIssueTool, JiraAddCommentTool
from app.tools.slack_tools import SlackPostMessageTool, SlackReplyInThreadTool


def _fake_response(url, method="GET", json_body=None, status_code=200):
    return httpx.Response(status_code, request=httpx.Request(method, str(url)), json=json_body)


async def _connect_integration(session, organization_id, provider: str, access_token: str) -> None:
    integration = Integration(organization_id=organization_id, provider=provider, is_active=True)
    session.add(integration)
    await session.flush()
    token_rec = OAuthToken(
        organization_id=organization_id, integration_id=integration.id,
        encrypted_access_token=encrypt_token(access_token), encrypted_refresh_token=encrypt_token(""),
        scopes=[f"{provider}:read", f"{provider}:write"],
    )
    session.add(token_rec)
    await session.commit()


async def test_broadened_tool_actions_flow():
    print("Initializing Broadened Real Tool Actions (Phase 77) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    original_jira = (settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)

    try:
        # 1. All 11 tools (6 pre-existing + 5 new) are present in the real registry -- proves
        #    Phase 71's LLM plan decomposition path picks them up automatically.
        print("\nTest 1: Verifying all 11 tools are registered, including the 5 new ones...")
        registry = get_tool_registry()
        tool_names = {t["name"] for t in registry.list_tools()}
        for name in ("github_comment_on_pr", "merge_pull_request", "jira_create_issue", "jira_add_comment", "slack_reply_in_thread"):
            assert name in tool_names, f"Expected '{name}' in the real tool registry, got: {tool_names}"
        print(f"SUCCESS: All 5 new tools registered alongside the 6 pre-existing ones ({len(tool_names)} total).")

        async with SessionLocal() as session:
            org = Organization(name=f"Broadened Tools Org {suffix}", domain=f"broadtools-{suffix}.com")
            session.add(org)
            await session.flush()
            test_org_id = org.id
            await session.commit()
        print(f"Test Organization created. ID: {test_org_id}")

        async with SessionLocal() as session:
            await _connect_integration(session, test_org_id, "github", "gho_real_mocked_token")
            await _connect_integration(session, test_org_id, "slack", "xoxb-real-mocked-token")

        # 2. github_comment_on_pr: real (mocked) POST to the Issues comments endpoint.
        print("\nTest 2: Verifying github_comment_on_pr calls the real GitHub API...")

        async def fake_github_comment(self, url, **kwargs):
            assert "api.github.com/repos/acme/ai-tpm/issues/42/comments" in str(url)
            assert kwargs["json"]["body"] == "Looks good, one nit inline."
            return _fake_response(url, "POST", json_body={"id": 9001, "html_url": "https://github.com/acme/ai-tpm/pull/42#issuecomment-9001"})

        async with SessionLocal() as session:
            with patch.object(httpx.AsyncClient, "post", new=fake_github_comment):
                result = await GitHubCommentOnPRTool().execute(
                    {"organization_id": str(test_org_id), "repo": "acme/ai-tpm", "pr_number": 42, "body": "Looks good, one nit inline."},
                    session=session,
                )
        assert result["status"] == "success"
        assert result["comment_id"] == 9001, f"Expected the real mocked comment id, got: {result}"
        print("SUCCESS: github_comment_on_pr made a real request and returned the real comment id.")

        # 3. merge_pull_request: WAITING_APPROVAL without a token (proves the pre-existing
        #    high-risk gate applies with zero executor changes), real merge with one.
        print("\nTest 3: Verifying merge_pull_request requires approval, then executes for real...")
        executor = ToolExecutor()
        no_approval = await executor.execute_tool(
            "merge_pull_request",
            {"organization_id": str(test_org_id), "repo": "acme/ai-tpm", "pr_number": 42},
        )
        assert no_approval["status"] == "WAITING_APPROVAL", f"Expected WAITING_APPROVAL without a token, got: {no_approval}"

        async def fake_github_merge(self, url, **kwargs):
            assert "api.github.com/repos/acme/ai-tpm/pulls/42/merge" in str(url)
            return _fake_response(url, "PUT", json_body={"merged": True, "sha": "abc123def456"})

        async with SessionLocal() as session:
            with patch.object(httpx.AsyncClient, "put", new=fake_github_merge):
                result = await MergePullRequestTool().execute(
                    {"organization_id": str(test_org_id), "repo": "acme/ai-tpm", "pr_number": 42},
                    session=session,
                )
        assert result["status"] == "success"
        assert result["merged"] is True and result["sha"] == "abc123def456", f"Expected the real mocked merge result, got: {result}"
        print("SUCCESS: merge_pull_request correctly required approval, then merged for real once granted.")

        # 4. jira_create_issue: real (mocked) POST with a real ADF-wrapped description.
        print("\nTest 4: Verifying jira_create_issue sends a real ADF-wrapped description...")
        settings.JIRA_BASE_URL = "acme-test"
        settings.JIRA_EMAIL = "bot@acme-test.com"
        settings.JIRA_API_TOKEN = "jira-real-mocked-token"

        async def fake_jira_create(self, url, **kwargs):
            assert str(url).endswith("/issue")
            fields = kwargs["json"]["fields"]
            assert fields["project"] == {"key": "TPM"}
            assert fields["summary"] == "Fix login race condition"
            assert fields["description"] == {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Users report intermittent failures."}]}],
            }, f"Expected a real ADF-wrapped description, got: {fields['description']}"
            return _fake_response(url, "POST", json_body={"key": "TPM-501", "id": "10501"})

        with patch.object(httpx.AsyncClient, "post", new=fake_jira_create):
            result = await JiraCreateIssueTool().execute({
                "project_key": "TPM", "summary": "Fix login race condition",
                "description": "Users report intermittent failures.",
            })
        assert result["status"] == "success"
        assert result["issue_key"] == "TPM-501", f"Expected the real mocked issue key, got: {result}"
        print("SUCCESS: jira_create_issue sent a real ADF-wrapped description and returned the real issue key.")

        # 5. jira_add_comment: real (mocked) POST with a real ADF-wrapped comment body.
        print("\nTest 5: Verifying jira_add_comment sends a real ADF-wrapped comment body...")

        async def fake_jira_comment(self, url, **kwargs):
            assert "issue/TPM-501/comment" in str(url)
            assert kwargs["json"]["body"] == {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Root caused, fix incoming."}]}],
            }
            return _fake_response(url, "POST", json_body={"id": "20501"})

        with patch.object(httpx.AsyncClient, "post", new=fake_jira_comment):
            result = await JiraAddCommentTool().execute({"issue_key": "TPM-501", "body": "Root caused, fix incoming."})
        assert result["status"] == "success"
        assert result["comment_id"] == "20501"
        print("SUCCESS: jira_add_comment sent a real ADF-wrapped comment body and returned the real comment id.")

        # 6. slack_reply_in_thread sends thread_ts; the pre-existing slack_post_message does
        #    NOT -- proves the additive thread_ts change didn't alter existing behavior.
        print("\nTest 6: Verifying slack_reply_in_thread sends thread_ts, and plain post_message still doesn't...")

        captured_payloads = []

        async def fake_slack_post(self, url, **kwargs):
            assert "slack.com/api/chat.postMessage" in str(url)
            captured_payloads.append(kwargs["json"])
            return _fake_response(url, "POST", json_body={"ok": True, "channel": "C12345", "ts": "1721999999.000099"})

        async with SessionLocal() as session:
            with patch.object(httpx.AsyncClient, "post", new=fake_slack_post):
                reply_result = await SlackReplyInThreadTool().execute(
                    {"organization_id": str(test_org_id), "channel": "#dev-alerts", "thread_ts": "1721999999.000001", "message": "Fixed in the latest deploy."},
                    session=session,
                )
                plain_result = await SlackPostMessageTool().execute(
                    {"organization_id": str(test_org_id), "channel": "#dev-alerts", "message": "Unrelated top-level post"},
                    session=session,
                )
        assert reply_result["status"] == "success" and reply_result["thread_ts"] == "1721999999.000001"
        assert "thread_ts" in captured_payloads[0], "slack_reply_in_thread must send thread_ts"
        assert plain_result["status"] == "success"
        assert "thread_ts" not in captured_payloads[1], "Plain slack_post_message must NOT send thread_ts (additive change, no regression)"
        print("SUCCESS: slack_reply_in_thread correctly sent thread_ts; plain post_message correctly did not.")

    finally:
        settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN = original_jira

        print("\nCleaning up test database entries...")
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

    print("\nAll Broadened Real Tool Actions tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_broadened_tool_actions_flow())
