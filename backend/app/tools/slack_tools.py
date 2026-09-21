from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import BaseTool
from app.integrations.slack import SlackConnector
from app.services.integration import IntegrationService


class SlackPostMessageTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="slack_post_message",
            description="Post a message notification to a Slack channel.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "organization_id": {"type": "string", "description": "Organization UUID (used to resolve the connected Slack OAuth token)"},
                    "channel": {"type": "string", "description": "Slack channel name or ID e.g. #dev-alerts"},
                    "message": {"type": "string", "description": "Message text to broadcast"}
                },
                "required": ["organization_id", "channel", "message"]
            }
        )

    async def execute(self, params: Dict[str, Any], session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        self.validate_parameters(params)
        channel = params["channel"]
        message = params["message"]

        try:
            if not session:
                raise ValueError("Database session required to resolve Slack credentials.")
            integration_service = IntegrationService(session)
            token = await integration_service.get_valid_oauth_token(UUID(str(params["organization_id"])), "slack")
            if not token:
                raise ValueError("Slack is not connected for this organization. Complete the OAuth flow first.")

            connector = SlackConnector(bot_token=token)
            result = await connector.post_message(channel=channel, text=message)
            return {
                "status": "success",
                "channel": result.get("channel", channel),
                "message": message,
                "ts": result.get("ts"),
            }
        except Exception as e:
            return {"status": "error", "channel": channel, "message": message, "error": str(e)}


class SlackReplyInThreadTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="slack_reply_in_thread",
            description="Reply to an existing message thread in a Slack channel.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "organization_id": {"type": "string", "description": "Organization UUID (used to resolve the connected Slack OAuth token)"},
                    "channel": {"type": "string", "description": "Slack channel name or ID e.g. #dev-alerts"},
                    "thread_ts": {"type": "string", "description": "Timestamp (ts) of the parent message to reply to"},
                    "message": {"type": "string", "description": "Reply text"},
                },
                "required": ["organization_id", "channel", "thread_ts", "message"],
            },
        )

    async def execute(self, params: Dict[str, Any], session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        self.validate_parameters(params)
        channel = params["channel"]
        thread_ts = params["thread_ts"]
        message = params["message"]

        try:
            if not session:
                raise ValueError("Database session required to resolve Slack credentials.")
            integration_service = IntegrationService(session)
            token = await integration_service.get_valid_oauth_token(UUID(str(params["organization_id"])), "slack")
            if not token:
                raise ValueError("Slack is not connected for this organization. Complete the OAuth flow first.")

            connector = SlackConnector(bot_token=token)
            result = await connector.post_message(channel=channel, text=message, thread_ts=thread_ts)
            return {
                "status": "success",
                "channel": result.get("channel", channel),
                "thread_ts": thread_ts,
                "ts": result.get("ts"),
            }
        except Exception as e:
            return {"status": "error", "channel": channel, "thread_ts": thread_ts, "error": str(e)}
