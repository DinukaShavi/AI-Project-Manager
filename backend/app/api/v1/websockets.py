from typing import Optional
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, resolve_user_from_access_token
from app.realtime.connection_manager import get_connection_manager

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """WebSocket streaming endpoint for live agent thoughts, outbox events, integration
    connection-status updates, and notifications, per api_contract.md section 17:
    "Authentication: Handled via JWT token query parameter: ws://api.domain/v1/ws?token=
    <JWT_TOKEN>". The organization a connection is scoped to is always derived from the
    authenticated user, never from client-supplied input -- an unauthenticated or invalid
    token is rejected before the connection is ever accepted, and no organization_id is
    ever read from the client."""
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        return

    manager = get_connection_manager()
    user = await resolve_user_from_access_token(db, token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired authentication token")
        return

    organization_id = user.organization_id
    await manager.connect(websocket, organization_id)

    # Connection Acknowledged, per api_contract.md's documented Server Response Envelope.
    await manager.send_personal_message(
        {
            "event": "connected",
            "status": "success",
            "details": {"user_id": str(user.id)},
        },
        websocket,
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type") or data.get("action") or "unknown"

            if msg_type == "ping":
                await manager.send_personal_message({"type": "pong"}, websocket)
            elif msg_type == "broadcast":
                payload = data.get("payload", {})
                await manager.broadcast_to_organization(
                    {
                        "type": "broadcast_event",
                        "sender_org": str(organization_id),
                        "payload": payload,
                    },
                    organization_id,
                )
            else:
                await manager.send_personal_message(
                    {
                        "type": "ack",
                        "received_type": msg_type,
                        "data": data,
                    },
                    websocket,
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, organization_id)
    except Exception:
        manager.disconnect(websocket, organization_id)
