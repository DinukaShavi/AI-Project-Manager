import uuid
from starlette.testclient import TestClient

import app.db.base # Register models
from app.main import app
from app.realtime.connection_manager import get_connection_manager

def test_realtime_system_flow():
    print("Initializing Real-Time WebSocket System validation tests...")

    # 1. Test ConnectionManager Singleton
    print("\nTest 1: Testing ConnectionManager instance...")
    manager = get_connection_manager()
    assert manager is not None
    print("SUCCESS: ConnectionManager singleton verified.")

    org_id = uuid.uuid4()
    client = TestClient(app)

    # 2. Test WebSocket Handshake & Communication Loop
    print(f"\nTest 2: Connecting to WebSocket at /api/v1/ws/{org_id}...")
    with client.websocket_connect(f"/api/v1/ws/{org_id}") as websocket:
        # Step A: Check handshake message
        handshake = websocket.receive_json()
        assert handshake["type"] == "connection_established"
        assert handshake["organization_id"] == str(org_id)
        print("SUCCESS: WebSocket handshake established.")

        # Step B: Test ping -> pong exchange
        print("\nTest 3: Testing WebSocket ping-pong frame exchange...")
        websocket.send_json({"type": "ping"})
        pong = websocket.receive_json()
        assert pong["type"] == "pong"
        print("SUCCESS: Received pong frame from WebSocket server.")

        # Step C: Test broadcast message
        print("\nTest 4: Testing WebSocket organization broadcast frame...")
        websocket.send_json({
            "type": "broadcast",
            "payload": {"event_name": "sprint_review_completed", "status": "success"}
        })
        broadcast_resp = websocket.receive_json()
        assert broadcast_resp["type"] == "broadcast_event"
        assert broadcast_resp["payload"]["event_name"] == "sprint_review_completed"
        print("SUCCESS: Received broadcast event frame.")

    print("\nAll Real-Time WebSocket System tests completed successfully!")

if __name__ == "__main__":
    test_realtime_system_flow()
