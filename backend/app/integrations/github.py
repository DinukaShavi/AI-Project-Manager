import hmac
import hashlib
from typing import Any, Dict, Optional
import httpx
from app.integrations.base import BaseConnector

class GitHubConnector(BaseConnector):
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.base_url = "https://api.github.com"

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify HMAC SHA-256 signature against X-Hub-Signature-256."""
        if not signature or not secret:
            return False
        
        # Header format: 'sha256=<hex_digest>'
        expected_sig = "sha256=" + hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_sig, signature)

    def parse_webhook_event(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """Normalize GitHub event payload into standardized system event format."""
        gh_event = headers.get("x-github-event", "unknown")
        action = payload.get("action", "")
        
        routing_key = f"github:{gh_event}"
        if action:
            routing_key += f":{action}"
            
        repo_name = payload.get("repository", {}).get("full_name", "")
        sender = payload.get("sender", {}).get("login", "")
        
        return {
            "routing_key": routing_key,
            "provider": "github",
            "repository": repo_name,
            "sender": sender,
            "raw_payload": payload
        }

    async def fetch_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch remote data using GitHub REST API."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-TPM-Integration"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
            
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/{endpoint.lstrip('/')}", headers=headers, params=params)
            response.raise_for_status()
            return response.json()
