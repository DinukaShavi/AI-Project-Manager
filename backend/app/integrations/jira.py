import hmac
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional
import httpx
from app.integrations.base import BaseConnector

class JiraConnector(BaseConnector):
    def __init__(
        self,
        domain: Optional[str] = None,
        api_token: Optional[str] = None,
        user_email: Optional[str] = None,
        access_token: Optional[str] = None,
        cloud_id: Optional[str] = None,
    ):
        self.domain = domain
        self.api_token = api_token
        self.user_email = user_email
        self.base_url = f"https://{domain}.atlassian.net/rest/api/3" if domain else ""
        # Second, independent auth mode: real per-organization OAuth Bearer tokens against
        # Atlassian's Cloud-ID-scoped proxy (api.atlassian.com/ex/jira/{cloud_id}/...), used
        # only by the real Issues/Sprints methods below -- deliberately separate from the
        # domain/api_token/user_email Basic-Auth path above, which stays exactly as-is for
        # every existing caller (transition_issue, list_projects, the backup-sync poller).
        self.access_token = access_token
        self.cloud_id = cloud_id
        self.oauth_base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3" if cloud_id else ""
        self.oauth_agile_base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/agile/1.0" if cloud_id else ""

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

    @staticmethod
    def _to_adf(text: str) -> Dict[str, Any]:
        """Wrap plain text in the minimal Atlassian Document Format Jira Cloud's v3 API
        requires for `description`/comment `body` fields -- the write-side counterpart of the
        ADF detection `ContextIngestionService._extract_jira` already does on the read side
        (context_ingestion.py), where a dict description is recognized as ADF and skipped
        rather than mis-indexed as plain text."""
        return {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}] if text else [],
        }

    async def create_issue(self, project_key: str, summary: str, description: str = "", issue_type: str = "Task") -> Dict[str, Any]:
        """Create a real Jira issue via POST /issue, on the same static-credential auth mode
        transition_issue already uses."""
        if not self.base_url or not self.api_token or not self.user_email:
            raise ValueError("Jira domain, user_email, and api_token are required for REST calls.")
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": self._to_adf(description),
                "issuetype": {"name": issue_type},
            }
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/issue",
                auth=(self.user_email, self.api_token),
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def add_comment(self, issue_key: str, body: str) -> Dict[str, Any]:
        """Add a real comment to a Jira issue via POST /issue/{key}/comment."""
        if not self.base_url or not self.api_token or not self.user_email:
            raise ValueError("Jira domain, user_email, and api_token are required for REST calls.")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/issue/{issue_key}/comment",
                auth=(self.user_email, self.api_token),
                headers={"Content-Type": "application/json"},
                json={"body": self._to_adf(body)},
            )
            response.raise_for_status()
            return response.json()

    def _oauth_headers(self) -> Dict[str, str]:
        if not self.access_token or not self.cloud_id:
            raise ValueError("A Jira OAuth access token and cloud_id are required for this call.")
        return {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}

    async def resolve_story_points_field_id(self) -> Optional[str]:
        """Best-effort resolve the custom field id Jira uses for Story Points on this site --
        Jira exposes it only as a per-instance custom field with no fixed id (e.g.
        "customfield_10016"), so this searches GET /field for a name match rather than
        guessing. Returns None (never a guessed id) if no confident match is found."""
        headers = self._oauth_headers()
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.oauth_base_url}/field", headers=headers)
            response.raise_for_status()
            fields = response.json()
        candidates = {"story points", "story point estimate"}
        for f in fields:
            if (f.get("name") or "").strip().lower() in candidates:
                return f.get("id")
        return None

    async def list_project_issues(
        self, project_key: str, story_points_field_id: Optional[str] = None, max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """Real issue backlog for a project via the OAuth-scoped GET /search (JQL)."""
        headers = self._oauth_headers()
        fields = "summary,status,priority,assignee"
        if story_points_field_id:
            fields += f",{story_points_field_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.oauth_base_url}/search",
                headers=headers,
                params={"jql": f"project = {project_key} ORDER BY updated DESC", "maxResults": max_results, "fields": fields},
            )
            response.raise_for_status()
            return response.json().get("issues", [])

    async def list_boards(self, project_key: str) -> List[Dict[str, Any]]:
        """Real Jira Software boards for a project via the Agile REST API."""
        headers = self._oauth_headers()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.oauth_agile_base_url}/board",
                headers=headers,
                params={"projectKeyOrId": project_key},
            )
            response.raise_for_status()
            return response.json().get("values", [])

    async def list_sprints(self, board_id: int) -> List[Dict[str, Any]]:
        """Real sprints for a board via the Agile REST API."""
        headers = self._oauth_headers()
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.oauth_agile_base_url}/board/{board_id}/sprint", headers=headers)
            response.raise_for_status()
            return response.json().get("values", [])

    async def get_sprint_story_points(self, sprint_id: int, story_points_field_id: str) -> Dict[str, float]:
        """Real completed/total story points for a sprint, summed from its real issues --
        Jira has no direct REST field for this, so it's computed from GET /sprint/{id}/issue."""
        headers = self._oauth_headers()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.oauth_agile_base_url}/sprint/{sprint_id}/issue",
                headers=headers,
                params={"fields": f"status,{story_points_field_id}"},
            )
            response.raise_for_status()
            issues = response.json().get("issues", [])

        total = 0.0
        completed = 0.0
        for issue in issues:
            points = (issue.get("fields") or {}).get(story_points_field_id)
            if not isinstance(points, (int, float)):
                continue
            total += points
            status_category = ((issue.get("fields") or {}).get("status") or {}).get("statusCategory") or {}
            if status_category.get("key") == "done":
                completed += points
        return {"completed_story_points": completed, "total_story_points": total}
