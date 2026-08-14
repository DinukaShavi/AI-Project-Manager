from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import BaseTool
from app.integrations.github import GitHubConnector
from app.services.integration import IntegrationService


async def _get_github_connector(session: Optional[AsyncSession], organization_id: str) -> GitHubConnector:
    """Resolve the org's connected GitHub OAuth token (exchange_code_for_token / Fernet-decrypted)
    and build a real, authenticated connector. Raises ValueError if not connected."""
    if not session:
        raise ValueError("Database session required to resolve GitHub credentials.")
    integration_service = IntegrationService(session)
    token = await integration_service.get_valid_oauth_token(UUID(str(organization_id)), "github")
    if not token:
        raise ValueError("GitHub is not connected for this organization. Complete the OAuth flow first.")
    return GitHubConnector(token=token)


class GitHubCreateIssueTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="github_create_issue",
            description="Create a new issue in a GitHub repository.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "organization_id": {"type": "string", "description": "Organization UUID (used to resolve the connected GitHub OAuth token)"},
                    "repo": {"type": "string", "description": "Repository full name e.g. owner/repo"},
                    "title": {"type": "string", "description": "Issue title"},
                    "body": {"type": "string", "description": "Issue body markdown"}
                },
                "required": ["organization_id", "repo", "title"]
            }
        )

    async def execute(self, params: Dict[str, Any], session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        self.validate_parameters(params)
        repo = params["repo"]
        title = params["title"]
        body = params.get("body", "")

        try:
            connector = await _get_github_connector(session, params["organization_id"])
            issue = await connector.create_issue(repo=repo, title=title, body=body)
            return {
                "status": "success",
                "issue_number": issue.get("number"),
                "url": issue.get("html_url"),
                "title": issue.get("title"),
                "body": issue.get("body"),
            }
        except Exception as e:
            return {"status": "error", "repo": repo, "title": title, "message": str(e)}


class GitHubGetPRDiffTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="github_get_pr_diff",
            description="Fetch code diff patch for a GitHub Pull Request.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "organization_id": {"type": "string", "description": "Organization UUID (used to resolve the connected GitHub OAuth token)"},
                    "repo": {"type": "string", "description": "Repository full name"},
                    "pr_number": {"type": "integer", "description": "Pull request number"}
                },
                "required": ["organization_id", "repo", "pr_number"]
            }
        )

    async def execute(self, params: Dict[str, Any], session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        self.validate_parameters(params)
        repo = params["repo"]
        pr_number = params["pr_number"]

        try:
            connector = await _get_github_connector(session, params["organization_id"])
            pr = await connector.get_pull_request(repo=repo, pr_number=pr_number)
            return {
                "status": "success",
                "repo": repo,
                "pr_number": pr_number,
                "files_changed": pr.get("changed_files"),
                "additions": pr.get("additions"),
                "deletions": pr.get("deletions"),
                "diff_summary": pr.get("title", ""),
            }
        except Exception as e:
            return {"status": "error", "repo": repo, "pr_number": pr_number, "message": str(e)}
