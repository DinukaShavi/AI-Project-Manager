import hmac
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
import httpx
from app.integrations.base import BaseConnector


def extract_meet_link(event: Dict[str, Any]) -> Optional[str]:
    """Pull the real Google Meet join URL out of a Calendar API event object, if it has one --
    shared by create_event's response and list_events' synced events, since both carry the
    same conferenceData/hangoutLink shape."""
    conference_data = event.get("conferenceData") or {}
    for entry_point in conference_data.get("entryPoints", []):
        if entry_point.get("entryPointType") == "video" and entry_point.get("uri"):
            return entry_point["uri"]
    return event.get("hangoutLink")

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
        attendee a real invite.

        Requests a real Google Meet link (conferenceDataVersion=1 + a createRequest) -- Phase
        65 -- rather than leaving every AI-TPM-created meeting without one."""
        if not self.access_token:
            raise ValueError("Google Calendar access_token is required for API calls.")

        payload: Dict[str, Any] = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time.isoformat()},
            "end": {"dateTime": end_time.isoformat()},
            "conferenceData": {
                "createRequest": {
                    "requestId": uuid.uuid4().hex,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        if attendee_emails:
            payload["attendees"] = [{"email": email} for email in attendee_emails]

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/calendars/{calendar_id}/events",
                headers=headers,
                json=payload,
                params={"conferenceDataVersion": 1},
            )
            response.raise_for_status()
            return response.json()

    async def query_freebusy(self, emails: List[str], time_min: datetime, time_max: datetime) -> Dict[str, List[Dict[str, str]]]:
        """Real busy intervals per email via POST /freeBusy -- the org's real Calendar OAuth
        token must have visibility into each calendar (true for the org's own members sharing
        a Workspace domain in the common case)."""
        if not self.access_token:
            raise ValueError("Google Calendar access_token is required for API calls.")
        if not emails:
            return {}

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": email} for email in emails],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/freeBusy", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        result: Dict[str, List[Dict[str, str]]] = {}
        for email, calendar_info in (data.get("calendars") or {}).items():
            result[email] = calendar_info.get("busy", [])
        return result
