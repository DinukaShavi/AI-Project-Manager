from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import BaseTool
from app.integrations.jira import JiraConnector
from app.core.config import settings


def _get_jira_connector() -> JiraConnector:
    """Jira is configured instance-wide via a static API token (settings.JIRA_BASE_URL /
    JIRA_EMAIL / JIRA_API_TOKEN), unlike GitHub/Slack which use per-organization OAuth —
    JiraConnector only supports Jira's classic Basic-Auth API-token flow, not OAuth 2.0 (3LO),
    so there is no per-org token to look up here."""
    domain = settings.JIRA_BASE_URL
    if domain and domain.startswith("http"):
        # Accept either a bare subdomain ("acme") or a full URL; extract the subdomain.
        domain = domain.split("//")[-1].split(".")[0]
    return JiraConnector(domain=domain, api_token=settings.JIRA_API_TOKEN, user_email=settings.JIRA_EMAIL)


class JiraGetIssueTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="jira_get_issue",
            description="Fetch details and status of a Jira issue ticket.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira ticket key e.g. TPM-42"}
                },
                "required": ["issue_key"]
            }
        )

    async def execute(self, params: Dict[str, Any], session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        self.validate_parameters(params)
        key = params["issue_key"]

        try:
            connector = _get_jira_connector()
            issue = await connector.get_issue(key)
            fields = issue.get("fields", {})
            return {
                "status": "success",
                "issue_key": key,
                "summary": fields.get("summary"),
                "issue_status": (fields.get("status") or {}).get("name"),
                "assignee": ((fields.get("assignee") or {}).get("displayName")),
                "priority": (fields.get("priority") or {}).get("name"),
            }
        except Exception as e:
            return {"status": "error", "issue_key": key, "message": str(e)}


class JiraUpdateIssueStatusTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="jira_update_issue_status",
            description="Transition Jira issue to a new status (e.g. In Progress, In Review, Done).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira ticket key"},
                    "status_name": {"type": "string", "description": "New status name"}
                },
                "required": ["issue_key", "status_name"]
            }
        )

    async def execute(self, params: Dict[str, Any], session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        self.validate_parameters(params)
        key = params["issue_key"]
        new_status = params["status_name"]

        try:
            connector = _get_jira_connector()
            result = await connector.transition_issue(key, new_status)
            return {
                "status": "success",
                "issue_key": key,
                "new_status": result.get("transitioned_to", new_status),
                "updated": True,
            }
        except Exception as e:
            return {"status": "error", "issue_key": key, "message": str(e), "updated": False}
