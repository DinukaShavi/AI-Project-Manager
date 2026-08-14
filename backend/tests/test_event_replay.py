import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User, Role
from app.models.event import Event
from app.models.audit import AuditLog
from app.db.session import SessionLocal
from app.core.security import get_password_hash
from app.events.redis_bus import get_event_bus
from tests._auth_helpers import create_authenticated_headers


async def test_event_replay_flow():
    print("Initializing Event Bus Replay validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    password = "ReplayPass123!"
    admin_a_email = f"replay-admin-a-{suffix}@example.com"
    admin_b_email = f"replay-admin-b-{suffix}@example.com"
    event_ids = []

    event_bus = get_event_bus()
    await event_bus.connect()

    received: list = []
    replay_seen = asyncio.Event()

    async def handler(msg_id: str, data: dict):
        received.append(data)
        if data.get("replay"):
            replay_seen.set()

    await event_bus.subscribe("github_stream", f"replay_test_group_{suffix}", "replay_consumer", handler)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Replay Org A {suffix}", domain=f"replay-a-{suffix}.com")
                org_b = Organization(name=f"Replay Org B {suffix}", domain=f"replay-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                org_admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                admin_a = User(organization_id=org_a_id, email=admin_a_email, full_name="Replay Admin A", hashed_password=get_password_hash(password))
                admin_a.roles.append(org_admin_role)
                admin_b = User(organization_id=org_b_id, email=admin_b_email, full_name="Replay Admin B", hashed_password=get_password_hash(password))
                admin_b.roles.append(org_admin_role)
                session.add_all([admin_a, admin_b])
                await session.commit()

                # A previously-ingested, already-processed event under Org A -- exactly the
                # kind of historical record a replay would target (e.g. a consumer that needs
                # to reprocess a webhook it missed).
                ev = Event(
                    organization_id=org_a_id,
                    routing_key="github:pull_request:opened",
                    payload={"pr_number": 42, "title": "Replay Test PR"},
                    processed=True,
                )
                session.add(ev)
                await session.commit()
                await session.refresh(ev)
                event_ids.append(ev.id)
            print(f"Test orgs/admins/event created. Org A={org_a_id} Org B={org_b_id} Event={event_ids[0]}")

            # Log in as the OrgAdmin users created directly above (create_authenticated_headers
            # registers a brand-new user, which isn't what we want here).
            res = await client.post("/api/v1/auth/login", json={"email": admin_a_email, "password": password})
            assert res.status_code == 200
            headers_a = {"Authorization": f"Bearer {res.json()['access_token']}"}

            res = await client.post("/api/v1/auth/login", json={"email": admin_b_email, "password": password})
            assert res.status_code == 200
            headers_b = {"Authorization": f"Bearer {res.json()['access_token']}"}

            # 1. A Developer-role user (Org A) is denied.
            print("\nTest 1: Verifying a Developer-role user is denied POST /events/replay (403)...")
            dev_headers = await create_authenticated_headers(client, org_a_id)
            res = await client.post("/api/v1/events/replay", json={}, headers=dev_headers)
            assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
            print("SUCCESS: Developer-role user correctly denied (403).")

            # 2. Org B's OrgAdmin cannot replay Org A's event, even with a matching pattern --
            # tenant identity comes only from the authenticated user, never client input.
            print("\nTest 2: Verifying Org B's OrgAdmin cannot replay Org A's event...")
            res = await client.post(
                "/api/v1/events/replay",
                json={"routing_key_pattern": "github:*"},
                headers=headers_b,
            )
            assert res.status_code == 202, res.text
            b_body = res.json()
            assert b_body["matched_count"] == 0
            assert b_body["replayed_count"] == 0
            print("SUCCESS: Org B's replay matched zero of Org A's events.")

            # 3. Org A's OrgAdmin can replay its own matching event, and the Event Bus
            # subscriber actually receives the re-published payload.
            print("\nTest 3: Verifying Org A's OrgAdmin can replay its own event...")
            res = await client.post(
                "/api/v1/events/replay",
                json={"routing_key_pattern": "github:*"},
                headers=headers_a,
            )
            assert res.status_code == 202, res.text
            a_body = res.json()
            assert a_body["matched_count"] == 1
            assert a_body["replayed_count"] == 1
            assert "replay_id" in a_body

            try:
                await asyncio.wait_for(replay_seen.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                raise AssertionError("Event Bus subscriber did not receive the replayed event within timeout.")
            replayed_msg = next(d for d in received if d.get("replay"))
            assert replayed_msg["routing_key"] == "github:pull_request:opened"
            assert replayed_msg["payload"]["title"] == "Replay Test PR"
            print("SUCCESS: Org A's replay matched and re-published its own event; subscriber received it.")

            # 4. A non-matching pattern narrows correctly to zero.
            print("\nTest 4: Verifying a non-matching routing_key_pattern returns zero matches...")
            res = await client.post(
                "/api/v1/events/replay",
                json={"routing_key_pattern": "slack:*"},
                headers=headers_a,
            )
            assert res.status_code == 202, res.text
            assert res.json()["matched_count"] == 0
            print("SUCCESS: Non-matching pattern correctly returned zero matches.")

            # 5. The replay action was audit-logged under Org A.
            print("\nTest 5: Verifying the replay action was audit-logged...")
            async with SessionLocal() as session:
                res_db = await session.execute(
                    select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "events:replay")
                )
                audit_rows = res_db.scalars().all()
                assert len(audit_rows) >= 1
            print(f"SUCCESS: {len(audit_rows)} 'events:replay' audit log entr(y/ies) recorded for Org A.")

        finally:
            print("\nCleaning up event replay test database entries...")
            await event_bus.disconnect()
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    audit_res = await session.execute(select(AuditLog).where(AuditLog.organization_id == oid))
                    for a in audit_res.scalars().all():
                        await session.delete(a)
                    event_res = await session.execute(select(Event).where(Event.organization_id == oid))
                    for e in event_res.scalars().all():
                        await session.delete(e)
                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()

                    org_res = await session.execute(select(Organization).where(Organization.id == oid))
                    db_org = org_res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Event Bus Replay tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_event_replay_flow())
