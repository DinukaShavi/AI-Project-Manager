from typing import Dict, List, Optional
from uuid import UUID
from fastapi import WebSocket

class ConnectionManager:
    """Central WebSocket Connection Manager handling org-scoped connections and live event broadcasts."""

    def __init__(self):
        self._active_connections: Dict[UUID, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, organization_id: UUID) -> None:
        """Accept WebSocket connection and register under organization ID."""
        await websocket.accept()
        if organization_id not in self._active_connections:
            self._active_connections[organization_id] = []
        self._active_connections[organization_id].append(websocket)

    def disconnect(self, websocket: WebSocket, organization_id: UUID) -> None:
        """Unregister and disconnect WebSocket from active list."""
        if organization_id in self._active_connections:
            if websocket in self._active_connections[organization_id]:
                self._active_connections[organization_id].remove(websocket)
            if not self._active_connections[organization_id]:
                del self._active_connections[organization_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket) -> None:
        """Send JSON payload to a single WebSocket client."""
        await websocket.send_json(message)

    async def broadcast_to_organization(self, message: dict, organization_id: UUID) -> None:
        """Broadcast JSON payload to all active WebSockets connected under an organization."""
        if organization_id in self._active_connections:
            # Copy to avoid mutation during iteration
            for connection in list(self._active_connections[organization_id]):
                try:
                    await connection.send_json(message)
                except Exception:
                    self.disconnect(connection, organization_id)


_connection_manager_instance: Optional[ConnectionManager] = None

def get_connection_manager() -> ConnectionManager:
    """Singleton getter for global ConnectionManager."""
    global _connection_manager_instance
    if _connection_manager_instance is None:
        _connection_manager_instance = ConnectionManager()
    return _connection_manager_instance
