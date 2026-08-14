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

    def _auth_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-TPM-Integration"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    async def fetch_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch remote data using GitHub REST API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/{endpoint.lstrip('/')}", headers=self._auth_headers(), params=params)
            response.raise_for_status()
            return response.json()

    async def create_issue(self, repo: str, title: str, body: str = "") -> Dict[str, Any]:
        """Create a real issue via POST /repos/{repo}/issues."""
        if not self.token:
            raise ValueError("A GitHub access token is required to create an issue.")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/repos/{repo}/issues",
                headers=self._auth_headers(),
                json={"title": title, "body": body}
            )
            response.raise_for_status()
            return response.json()

    async def get_authenticated_user(self) -> Dict[str, Any]:
        """Fetch the connected token's own real GitHub identity via GET /user -- the stable
        numeric `id` and `login` this deployment did not previously capture anywhere."""
        if not self.token:
            raise ValueError("A GitHub access token is required to resolve the authenticated user.")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/user", headers=self._auth_headers())
            response.raise_for_status()
            return response.json()

    async def list_repositories(self) -> list:
        """List real repositories the connected token can access (personal + any
        organization repos in scope) via GET /user/repos, per api_contract.md section 4.A's
        documented "select GitHub repositories to link" step."""
        if not self.token:
            raise ValueError("A GitHub access token is required to list repositories.")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/user/repos",
                headers=self._auth_headers(),
                params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
            )
            response.raise_for_status()
            return response.json()

    async def get_pull_request(self, repo: str, pr_number: int) -> Dict[str, Any]:
        """Fetch pull request details (including additions/deletions/changed_files) via
        GET /repos/{repo}/pulls/{pr_number}."""
        if not self.token:
            raise ValueError("A GitHub access token is required to fetch a pull request.")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/repos/{repo}/pulls/{pr_number}", headers=self._auth_headers())
            response.raise_for_status()
            return response.json()
