import hmac
import hashlib
from typing import Any, Dict, Optional
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
