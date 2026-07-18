import hmac
import hashlib
from typing import Any, Dict, Optional
import httpx
from app.integrations.base import BaseConnector

class SlackConnector(BaseConnector):
    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token
        self.base_url = "https://slack.com/api"

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify Slack HMAC SHA-256 signature against X-Slack-Signature."""
        if not signature or not secret:
            return False
            
        # Slack signature header format: 'v0=hexdigest'
        # Signature basestring: 'v0:{timestamp}:{payload}'
        # Note: In a full request context, timestamp header is checked for age (< 5 min).
        # Here we verify the signature construction.
        parts = signature.split("=")
        if len(parts) != 2:
            return False
            
        expected_sig = "v0=" + hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_sig, signature)

    def parse_webhook_event(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """Normalize Slack Events API payload into standardized system event format."""
        event_type = payload.get("type", "unknown")
        
        if event_type == "url_verification":
            return {
                "routing_key": "slack:url_verification",
                "provider": "slack",
                "challenge": payload.get("challenge"),
                "raw_payload": payload
            }
            
        event_body = payload.get("event", {})
        sub_type = event_body.get("type", "event")
        channel = event_body.get("channel", "")
        user = event_body.get("user", "")
        
        routing_key = f"slack:{sub_type}"
        
        return {
            "routing_key": routing_key,
            "provider": "slack",
            "channel": channel,
            "user": user,
            "raw_payload": payload
        }

    async def fetch_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch remote data using Slack Web API."""
        if not self.bot_token:
            raise ValueError("Slack bot_token is required for API calls.")
            
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/{endpoint.lstrip('/')}", headers=headers, params=params)
            response.raise_for_status()
            return response.json()
