import hmac
from datetime import datetime
from typing import Any, Dict, List, Optional
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

    async def list_events(self, time_min: datetime, time_max: datetime, calendar_id: str = "primary") -> List[Dict[str, Any]]:
        """List events on a calendar within [time_min, time_max), per the Google Calendar v3
        `events.list` API. Used by the documented "Sync Calendar Events Range" endpoint, since
        Calendar is polling-driven (per detailed_component_architecture.md's Sync Frequency
        Matrix) rather than webhook-driven — push notifications only signal that *something*
        changed, they carry no event data."""
        data = await self.fetch_data(
            f"calendars/{calendar_id}/events",
            params={
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        return data.get("items", [])

    async def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        attendee_emails: Optional[List[str]] = None,
        description: str = "",
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Create a real event via POST .../events -- the write side `list_events` never had.
        Uses the same `calendar.events` OAuth scope already granted for reading; that scope
        covers both read and write, so no additional consent is required. Google emails each
        attendee a real invite."""
        if not self.access_token:
            raise ValueError("Google Calendar access_token is required for API calls.")

        payload: Dict[str, Any] = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time.isoformat()},
            "end": {"dateTime": end_time.isoformat()},
        }
        if attendee_emails:
            payload["attendees"] = [{"email": email} for email in attendee_emails]

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/calendars/{calendar_id}/events", headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
