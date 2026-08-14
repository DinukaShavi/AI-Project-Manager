import asyncio
import uuid
from starlette.testclient import TestClient

import app.db.base # Register models
from app.main import app
from app.core.security import get_password_hash, create_access_token
from app.realtime.connection_manager import get_connection_manager
from app.models.tenant import Organization, User
from app.db.session import SessionLocal, async_engine
from sqlalchemy import select


async def _create_user(session, org_id, email):
    user = User(organization_id=org_id, email=email, full_name="Realtime Test User", hashed_password=get_password_hash("TestPass123!"))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def test_realtime_system_flow():
    print("Initializing Real-Time WebSocket System validation tests...")

    # 1. Test ConnectionManager Singleton
    print("\nTest 1: Testing ConnectionManager instance...")
    manager = get_connection_manager()
    assert manager is not None
    print("SUCCESS: ConnectionManager singleton verified.")

    org_id = None
    user_id = None
    access_token = None

    # This test runs inside its own OS thread (via asyncio.to_thread in run_all_tests.py,
    # since starlette.testclient.TestClient's WebSocket support is sync-only) and creates
    # a brand-new event loop here via asyncio.run(). The global SQLAlchemy engine's
    # connection pool may already hold connections bound to the MAIN thread's loop from
    # earlier phases in the same process -- dispose it first so every connection this
    # test's own loop(s) use is established fresh, never borrowed across loops/threads.
    asyncio.run(async_engine.dispose())

    async def _setup():
        nonlocal org_id, user_id, access_token
        async with SessionLocal() as session:
            org = Organization(name=f"Realtime Test Org {uuid.uuid4().hex[:6]}", domain=f"realtime-{uuid.uuid4().hex[:6]}.com")
            session.add(org)
            await session.flush()
            org_id = org.id
            await session.commit()
            user = await _create_user(session, org_id, f"realtime-{uuid.uuid4().hex[:6]}@example.com")
            user_id = user.id
        access_token = create_access_token(subject=str(user_id))

    asyncio.run(_setup())
    # TestClient's WebSocket support runs the ASGI app on its own internal event loop
    # (distinct from the one asyncio.run(_setup()) just used and closed) -- dispose the
    # SQLAlchemy engine's pooled connections first so the WebSocket route establishes
    # fresh ones under TestClient's loop instead of reusing connections bound to a dead one.
    asyncio.run(async_engine.dispose())
    client = TestClient(app)

    # 2. Per api_contract.md section 17: authentication is via JWT ?token= query param at
    # /api/v1/ws -- a connection with NO token must be rejected before ever being accepted.
    print("\nTest 2: Verifying an unauthenticated WebSocket connection is rejected...")
    rejected = False
    try:
        with client.websocket_connect("/api/v1/ws"):
            pass
    except Exception:
        rejected = True
    assert rejected, "Expected the connection to be rejected without a token"
    print("SUCCESS: Unauthenticated WebSocket connection correctly rejected.")

    # 3. An invalid/garbage token must also be rejected.
    print("\nTest 3: Verifying an invalid token is rejected...")
    rejected = False
    try:
        with client.websocket_connect("/api/v1/ws?token=not-a-real-jwt"):
            pass
    except Exception:
        rejected = True
    assert rejected, "Expected the connection to be rejected for an invalid token"
    print("SUCCESS: Invalid token correctly rejected.")

    # 4. A valid token succeeds and the handshake matches the documented envelope exactly:
    # {"event": "connected", "status": "success", "details": {"user_id": ...}}.
    print(f"\nTest 4: Connecting to WebSocket at /api/v1/ws with a valid token...")
    with client.websocket_connect(f"/api/v1/ws?token={access_token}") as websocket:
        handshake = websocket.receive_json()
        assert handshake["event"] == "connected"
        assert handshake["status"] == "success"
        assert handshake["details"]["user_id"] == str(user_id)
        print("SUCCESS: WebSocket handshake matches the documented api_contract.md envelope.")

        # Step B: Test ping -> pong exchange
        print("\nTest 5: Testing WebSocket ping-pong frame exchange...")
        websocket.send_json({"type": "ping"})
        pong = websocket.receive_json()
        assert pong["type"] == "pong"
        print("SUCCESS: Received pong frame from WebSocket server.")

        # Step C: Test broadcast message, scoped to the authenticated user's own organization
        # (never a client-supplied org id).
        print("\nTest 6: Testing WebSocket organization broadcast frame...")
        websocket.send_json({
            "type": "broadcast",
            "payload": {"event_name": "sprint_review_completed", "status": "success"}
        })
        broadcast_resp = websocket.receive_json()
        assert broadcast_resp["type"] == "broadcast_event"
        assert broadcast_resp["sender_org"] == str(org_id)
        assert broadcast_resp["payload"]["event_name"] == "sprint_review_completed"
        print("SUCCESS: Received broadcast event frame scoped to the authenticated user's own organization.")

    asyncio.run(async_engine.dispose())

    async def _cleanup():
        async with SessionLocal() as session:
            u_res = await session.execute(select(User).where(User.id == user_id))
            u = u_res.scalar_one_or_none()
            if u:
                await session.delete(u)
            await session.commit()
            o_res = await session.execute(select(Organization).where(Organization.id == org_id))
            o = o_res.scalar_one_or_none()
            if o:
                await session.delete(o)
            await session.commit()

    asyncio.run(_cleanup())

    # asyncio.run() above tore down its own loop on return, which would strand any
    # connections it pooled -- dispose once more so control returns to the caller (the
    # master suite's main loop, running the NEXT phase) with a completely clean pool.
    asyncio.run(async_engine.dispose())

    print("\nAll Real-Time WebSocket System tests completed successfully!")

if __name__ == "__main__":
    test_realtime_system_flow()
