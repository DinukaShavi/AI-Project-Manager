import hmac
from typing import Any, Dict, Optional
import httpx
from app.integrations.base import BaseConnector

class GoogleCalendarConnector(BaseConnector):
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.base_url = "https://www.googleapis.com/calendar/v3"

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify Google Channel Token against X-Goog-Channel-Token."""
        if not signature or not secret:
            return False
        return hmac.compare_digest(signature, secret)

    def parse_webhook_event(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """Normalize Google Calendar Push Notification headers into standardized system event format."""
        resource_state = headers.get("x-goog-resource-state", "changed")
        channel_id = headers.get("x-goog-channel-id", "")
        resource_id = headers.get("x-goog-resource-id", "")
        
        routing_key = f"calendar:event:{resource_state}"
        
        return {
            "routing_key": routing_key,
            "provider": "google_calendar",
            "channel_id": channel_id,
            "resource_id": resource_id,
            "raw_payload": payload
        }

    async def fetch_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch remote data using Google Calendar v3 REST API."""
        if not self.access_token:
            raise ValueError("Google Calendar access_token is required for API calls.")
            
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/{endpoint.lstrip('/')}", headers=headers, params=params)
            response.raise_for_status()
            return response.json()
