from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import BaseTool

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
        return {
            "status": "success",
            "issue_key": key,
            "summary": "Fix database transaction deadlock in event outbox worker loop",
            "issue_status": "In Progress",
            "assignee": "Alice Developer",
            "priority": "High"
        }


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
        return {
            "status": "success",
            "issue_key": key,
            "previous_status": "In Progress",
            "new_status": new_status,
            "updated": True
        }
