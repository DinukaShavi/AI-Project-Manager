import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.models.tenant import Organization, User, Role
from app.models.event import Event
from app.db.session import SessionLocal
from app.core.security import get_password_hash
from app.services.outbox import OutboxService, MAX_DELIVERY_ATTEMPTS
from tests._auth_helpers import create_authenticated_headers

PASSWORD = "DlqPass123!"


async def _seed_event(org_id, routing_key="github:push") -> uuid.UUID:
    async with SessionLocal() as session:
        ev = Event(
            organization_id=org_id,
            routing_key=routing_key,
            payload={"probe": "dlq-test"},
            processed=False,
        )
        session.add(ev)
        await session.commit()
        return ev.id


async def test_event_dlq_flow():
    print("Initializing Event Bus Dead Letter Queue (Phase 87 / Milestone 4) validation tests...")

    org_id = None
    other_org_id = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org = Organization(name=f"DLQ Org {uuid.uuid4().hex[:6]}", domain=f"dlq-{uuid.uuid4().hex[:6]}.com")
                other = Organization(name=f"DLQ Other {uuid.uuid4().hex[:6]}", domain=f"dlqo-{uuid.uuid4().hex[:6]}.com")
                session.add_all([org, other])
                await session.commit()
                org_id = org.id
                other_org_id = other.id

            # 1. A failing publish must persist its retry bookkeeping.
            #    Pre-Phase-87 the commit was guarded by `if processed_count > 0`, so when every
            #    event in the batch failed, retry_count/error_log were silently rolled back.
            print("\nTest 1: Verifying a failed publish persists retry_count and error_log...")
            event_id = await _seed_event(org_id)

            failing_bus = AsyncMock()
            failing_bus.publish.side_effect = ConnectionError("broker unreachable")

            async with SessionLocal() as session:
                svc = OutboxService(session)
                svc.event_bus = failing_bus
                processed = await svc.process_outbox()
            assert processed == 0

            async with SessionLocal() as session:
                ev = await session.get(Event, event_id)
                assert ev.retry_count == 1, (
                    f"retry_count was not persisted (got {ev.retry_count}). The failure "
                    "bookkeeping was rolled back -- the pre-Phase-87 defect."
                )
                assert ev.error_log and "broker unreachable" in ev.error_log
                assert ev.dead_lettered_at is None
            print("SUCCESS: retry_count and error_log survive a batch in which nothing succeeded.")

            # 2. After MAX_DELIVERY_ATTEMPTS the event routes to the DLQ and stops being polled.
            print(f"\nTest 2: Verifying routing to the DLQ after {MAX_DELIVERY_ATTEMPTS} failures...")
            for _ in range(MAX_DELIVERY_ATTEMPTS - 1):
                async with SessionLocal() as session:
                    svc = OutboxService(session)
                    svc.event_bus = failing_bus
                    await svc.process_outbox()

            async with SessionLocal() as session:
                ev = await session.get(Event, event_id)
                assert ev.retry_count >= MAX_DELIVERY_ATTEMPTS, ev.retry_count
                assert ev.dead_lettered_at is not None, "Event was never routed to the DLQ."
            print(f"SUCCESS: Event routed to the DLQ at {MAX_DELIVERY_ATTEMPTS} attempts.")

            # A dead-lettered event must no longer be picked up by the poller, so a poison
            # pill stops consuming retry cycles forever.
            calls_before = failing_bus.publish.await_count
            async with SessionLocal() as session:
                svc = OutboxService(session)
                svc.event_bus = failing_bus
                await svc.process_outbox()
            assert failing_bus.publish.await_count == calls_before, (
                "A dead-lettered event was retried again -- it is still in the polling set."
            )
            print("SUCCESS: Dead-lettered events are excluded from further polling.")

            # 3. GET /api/v1/events/dlq (Milestone 4's specified admin view).
            print("\nTest 3: Verifying GET /api/v1/events/dlq requires auth + admin role...")
            res_anon = await client.get("/api/v1/events/dlq")
            assert res_anon.status_code in (401, 403), res_anon.status_code

            dev_headers = await create_authenticated_headers(client, org_id)
            res_dev = await client.get("/api/v1/events/dlq", headers=dev_headers)
            assert res_dev.status_code == 403, f"A Developer must not read the DLQ: {res_dev.text}"

            admin_email = f"dlq-admin-{uuid.uuid4().hex[:8]}@example.com"
            async with SessionLocal() as session:
                admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                admin = User(
                    organization_id=org_id,
                    email=admin_email,
                    full_name="DLQ Admin",
                    hashed_password=get_password_hash(PASSWORD),
                )
                admin.roles.append(admin_role)
                session.add(admin)
                await session.commit()

            res_login = await client.post("/api/v1/auth/login", json={"email": admin_email, "password": PASSWORD})
            assert res_login.status_code == 200, res_login.text
            admin_headers = {"Authorization": f"Bearer {res_login.json()['access_token']}"}

            res_dlq = await client.get("/api/v1/events/dlq", headers=admin_headers)
            assert res_dlq.status_code == 200, res_dlq.text
            body = res_dlq.json()
            listed = [e for e in body["events"] if e["id"] == str(event_id)]
            assert listed, f"The dead-lettered event is not listed in the DLQ: {body}"
            assert "broker unreachable" in (listed[0]["error_log"] or "")
            print("SUCCESS: The DLQ view lists the failed event with its last error, admin-only.")

            # 4. Tenant isolation: another org's admin must not see this event.
            print("\nTest 4: Verifying DLQ entries are tenant-scoped...")
            other_admin_email = f"dlq-other-{uuid.uuid4().hex[:8]}@example.com"
            async with SessionLocal() as session:
                admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                other_admin = User(
                    organization_id=other_org_id,
                    email=other_admin_email,
                    full_name="Other DLQ Admin",
                    hashed_password=get_password_hash(PASSWORD),
                )
                other_admin.roles.append(admin_role)
                session.add(other_admin)
                await session.commit()

            res_login2 = await client.post("/api/v1/auth/login", json={"email": other_admin_email, "password": PASSWORD})
            other_headers = {"Authorization": f"Bearer {res_login2.json()['access_token']}"}

            res_other = await client.get("/api/v1/events/dlq", headers=other_headers)
            assert res_other.status_code == 200, res_other.text
            assert not [e for e in res_other.json()["events"] if e["id"] == str(event_id)], \
                "Another organization's dead-lettered event leaked into this org's DLQ view."

            res_other_requeue = await client.post(f"/api/v1/events/dlq/{event_id}/requeue", headers=other_headers)
            assert res_other_requeue.status_code == 404, \
                f"Cross-tenant requeue must 404, got {res_other_requeue.status_code}"
            print("SUCCESS: DLQ listing and requeue are both tenant-scoped.")

            # 5. Requeue returns the event to the outbox so recovery is actually possible.
            print("\nTest 5: Verifying requeue returns a dead-lettered event to the outbox...")
            res_rq = await client.post(f"/api/v1/events/dlq/{event_id}/requeue", headers=admin_headers)
            assert res_rq.status_code == 200, res_rq.text

            async with SessionLocal() as session:
                ev = await session.get(Event, event_id)
                assert ev.dead_lettered_at is None
                assert ev.retry_count == 0

            # With a working broker it now publishes successfully.
            ok_bus = AsyncMock()
            async with SessionLocal() as session:
                svc = OutboxService(session)
                svc.event_bus = ok_bus
                processed = await svc.process_outbox()
            assert processed >= 1, "Requeued event was not re-delivered."

            async with SessionLocal() as session:
                ev = await session.get(Event, event_id)
                assert ev.processed is True
            print("SUCCESS: A requeued event is re-delivered and marked processed.")

        finally:
            print("\nCleaning up DLQ test database entries...")
            for oid in (org_id, other_org_id):
                if not oid:
                    continue
                async with SessionLocal() as session:
                    evs = await session.execute(select(Event).where(Event.organization_id == oid))
                    for e in evs.scalars().all():
                        await session.delete(e)
                    users = await session.execute(select(User).where(User.organization_id == oid))
                    for u in users.scalars().all():
                        await session.delete(u)
                    org_row = await session.get(Organization, oid)
                    if org_row:
                        await session.delete(org_row)
                    await session.commit()
            print("Cleanup completed.")

    print("\nAll Event Bus Dead Letter Queue tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_event_dlq_flow())
