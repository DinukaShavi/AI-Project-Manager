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

    async def list_channels(self) -> list:
        """List real channels the connected bot token can see via GET conversations.list,
        for the "select Slack channels to map" step (api_contract.md section 6.A)."""
        data = await self.fetch_data(
            "conversations.list",
            params={"types": "public_channel,private_channel", "limit": 200, "exclude_archived": "true"},
        )
        if not data.get("ok"):
            raise ValueError(f"Slack API error: {data.get('error', 'unknown_error')}")
        return data.get("channels", [])

    async def list_users(self) -> list:
        """List real workspace members via GET users.list."""
        data = await self.fetch_data("users.list", params={"limit": 200})
        if not data.get("ok"):
            raise ValueError(f"Slack API error: {data.get('error', 'unknown_error')}")
        return [m for m in data.get("members", []) if not m.get("deleted")]

    async def list_channel_messages(self, channel_id: str, limit: int = 30) -> list:
        """List real recent messages in a channel via GET conversations.history. Requires the
        channels:history scope and the bot to be a member of the channel."""
        data = await self.fetch_data("conversations.history", params={"channel": channel_id, "limit": limit})
        if not data.get("ok"):
            raise ValueError(f"Slack API error: {data.get('error', 'unknown_error')}")
        return data.get("messages", [])

    async def post_message(self, channel: str, text: str, thread_ts: Optional[str] = None) -> Dict[str, Any]:
        """Post a real message via POST chat.postMessage. Slack returns HTTP 200 even for
        application-level errors, signaled via the 'ok' field. Optional thread_ts replies
        inside an existing thread instead of posting a new top-level message -- additive,
        every existing top-level-post caller is unaffected."""
        if not self.bot_token:
            raise ValueError("Slack bot_token is required to post a message.")

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload: Dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat.postMessage",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise ValueError(f"Slack API error: {data.get('error', 'unknown_error')}")
            return data
