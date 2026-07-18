from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.realtime.connection_manager import get_connection_manager

router = APIRouter()

@router.websocket("/ws/{organization_id}")
async def websocket_endpoint(websocket: WebSocket, organization_id: UUID):
    """WebSocket streaming endpoint for live agent thoughts, outbox events, and notifications."""
    manager = get_connection_manager()
    await manager.connect(websocket, organization_id)
    
    # Send connection handshake confirmation
    await manager.send_personal_message(
        {
            "type": "connection_established",
            "organization_id": str(organization_id),
            "message": "Connected to AI-TPM Real-Time Event Stream"
        },
        websocket
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "unknown")

            if msg_type == "ping":
                await manager.send_personal_message({"type": "pong"}, websocket)
            elif msg_type == "broadcast":
                payload = data.get("payload", {})
                await manager.broadcast_to_organization(
                    {
                        "type": "broadcast_event",
                        "sender_org": str(organization_id),
                        "payload": payload
                    },
                    organization_id
                )
            else:
                await manager.send_personal_message(
                    {
                        "type": "ack",
                        "received_type": msg_type,
                        "data": data
                    },
                    websocket
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, organization_id)
    except Exception:
        manager.disconnect(websocket, organization_id)
