import hmac
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional
import httpx
from app.integrations.base import BaseConnector

class JiraConnector(BaseConnector):
    def __init__(self, domain: Optional[str] = None, api_token: Optional[str] = None, user_email: Optional[str] = None):
        self.domain = domain
        self.api_token = api_token
        self.user_email = user_email
        self.base_url = f"https://{domain}.atlassian.net/rest/api/3" if domain else ""

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify Jira webhook signature or secret header."""
        if not secret:
            return True # Jira webhooks can use custom query secret validation if secret header isn't configured
        if not signature:
            return False
        return hmac.compare_digest(signature, secret)

    def parse_webhook_event(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """Normalize Jira event payload into standardized system event format."""
        jira_event = payload.get("webhookEvent", "unknown").replace(":", "_")
        issue = payload.get("issue", {})
        issue_key = issue.get("key", "")
        project_key = issue.get("fields", {}).get("project", {}).get("key", "")
        user = payload.get("user", {}).get("displayName", "")
        
        routing_key = f"jira:{jira_event}"
        
        return {
            "routing_key": routing_key,
            "provider": "jira",
            "project_key": project_key,
            "issue_key": issue_key,
            "user": user,
            "raw_payload": payload
        }

    async def fetch_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch remote data using Jira REST API v3."""
        if not self.base_url or not self.api_token or not self.user_email:
            raise ValueError("Jira domain, user_email, and api_token are required for REST calls.")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                auth=(self.user_email, self.api_token),
                headers={"Accept": "application/json"},
                params=params
            )
            response.raise_for_status()
            return response.json()

    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Fetch a single issue's fields via GET /issue/{key}."""
        return await self.fetch_data(f"issue/{issue_key}")

    async def list_projects(self) -> List[Dict[str, Any]]:
        """List every Jira project visible to this connection, per api_contract.md section
        5.A ("Import Jira Projects List"). Uses Atlassian's current recommended
        /project/search endpoint (paginated via startAt/isLast), not the older unpaginated
        /project endpoint, and follows pagination through to the end rather than returning
        only the first page."""
        projects: List[Dict[str, Any]] = []
        start_at = 0
        max_results = 50
        while True:
            data = await self.fetch_data("project/search", params={"startAt": start_at, "maxResults": max_results})
            values = data.get("values", [])
            projects.extend(values)
            if data.get("isLast", True) or not values:
                break
            start_at += max_results
        return projects

    async def search_recently_updated_issues(self, since: Optional[datetime] = None, max_results: int = 50) -> List[Dict[str, Any]]:
        """Delta-sync query for the documented backup-poll cron (system_architecture_design.md's
        Sync frequency matrix: "Jira = webhook + 4-hour backup cron", delta-synced via
        modified_after / last_synced_at). Falls back to the last 4 hours when there is no prior
        watermark (e.g. this integration has never been synced before)."""
        if since:
            jql_time = since.strftime("%Y/%m/%d %H:%M")
            jql = f'updated >= "{jql_time}" ORDER BY updated ASC'
        else:
            jql = "updated >= -4h ORDER BY updated ASC"

        data = await self.fetch_data(
            "search",
            params={"jql": jql, "maxResults": max_results, "fields": "summary,status,priority,assignee,project,updated"}
        )
        return data.get("issues", [])

    async def transition_issue(self, issue_key: str, status_name: str) -> Dict[str, Any]:
        """Transition an issue to a new status by name. Jira requires resolving the target
        status to a transition ID first (GET /issue/{key}/transitions), then POSTing it."""
        if not self.base_url or not self.api_token or not self.user_email:
            raise ValueError("Jira domain, user_email, and api_token are required for REST calls.")

        async with httpx.AsyncClient() as client:
            trans_res = await client.get(
                f"{self.base_url}/issue/{issue_key}/transitions",
                auth=(self.user_email, self.api_token),
                headers={"Accept": "application/json"},
            )
            trans_res.raise_for_status()
            transitions = trans_res.json().get("transitions", [])
            match = next(
                (t for t in transitions if status_name.lower() in (t.get("name", "").lower(), t.get("to", {}).get("name", "").lower())),
                None
            )
            if not match:
                available = [t.get("name") for t in transitions]
                raise ValueError(f"No transition to status '{status_name}' is available for '{issue_key}'. Available: {available}")

            post_res = await client.post(
                f"{self.base_url}/issue/{issue_key}/transitions",
                auth=(self.user_email, self.api_token),
                headers={"Content-Type": "application/json"},
                json={"transition": {"id": match["id"]}},
            )
            post_res.raise_for_status()
            return {"issue_key": issue_key, "transitioned_to": match.get("to", {}).get("name", status_name)}
