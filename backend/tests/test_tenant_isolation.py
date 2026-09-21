import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.core.tenant_isolation import (
    get_tenant_isolation_engine,
    TenantIsolationEngine
)
from app.models.tenant import Organization, User, Role
from app.db.session import SessionLocal
from app.core.security import get_password_hash
from tests._auth_helpers import create_authenticated_headers

async def test_tenant_isolation_flow():
    print("Initializing Multi-Tenant Schema & Virtual Isolation Engine validation tests...")
    engine = get_tenant_isolation_engine()
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())

    # 1. Test Key & Channel Namespace Formatting
    print("\nTest 1: Testing key namespace partitioning across Redis, Event Bus, Queues & WebSockets...")
    redis_key = engine.partition_redis_key(tenant_a, "user_session:100")
    assert redis_key == f"tenant:{tenant_a}:user_session:100"

    event_key = engine.partition_routing_key(tenant_a, "task.created")
    assert event_key == f"tenant.{tenant_a}.task.created"

    worker_queue = engine.partition_worker_queue(tenant_a, priority="high")
    assert worker_queue == f"tenant_{tenant_a}_dedicated_high_priority_queue"

    ws_chan = engine.partition_ws_channel(tenant_a, "notifications")
    assert ws_chan == f"ws:tenant:{tenant_a}:notifications"

    print("SUCCESS: Tenant namespace partitioning formatting verified.")

    # 2. Test Vector Similarity Search Namespace Injection
    print("\nTest 2: Testing pgvector query filter tenant_id injection...")
    query_filter = {"category": "documentation"}
    enforced = engine.validate_vector_query_filter(tenant_a, query_filter)
    assert enforced["tenant_id"] == tenant_a
    assert enforced["category"] == "documentation"
    print("SUCCESS: Vector search query filter successfully injected tenant isolation boundaries.")

    # 3. Test Cross-Tenant Access Audit
    print("\nTest 3: Testing Cross-Tenant Access Audit & Boundary Enforcement...")
    # Same tenant -> Allowed
    ok_same, msg_same = engine.audit_cross_tenant_access(tenant_a, tenant_a)
    assert ok_same is True
    assert msg_same == "SAME_TENANT_ACCESS_ALLOWED"

    # Cross tenant without super admin -> Denied
    ok_cross, msg_cross = engine.audit_cross_tenant_access(tenant_a, tenant_b, is_super_admin=False)
    assert ok_cross is False
    assert "TENANT_ISOLATION_VIOLATION" in msg_cross

    # Cross tenant with super admin -> Allowed
    ok_admin, msg_admin = engine.audit_cross_tenant_access(tenant_a, tenant_b, is_super_admin=True)
    assert ok_admin is True
    assert msg_admin == "SUPER_ADMIN_AUDIT_PERMITTED"

    print("SUCCESS: Cross-tenant security access audit verified.")

    # 4. Test REST API Endpoints require real authentication, derive tenant_id server-side,
    #    and cannot be tricked by a client-supplied is_super_admin flag (Phase 83).
    print("\nTest 4: Testing Tenant Isolation HTTP REST API endpoints...")
    real_org_a_id = None
    real_org_b_id = None
    admin_user_id = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Tenant Iso Org A {uuid.uuid4().hex[:6]}", domain=f"tiso-a-{uuid.uuid4().hex[:6]}.com")
                org_b = Organization(name=f"Tenant Iso Org B {uuid.uuid4().hex[:6]}", domain=f"tiso-b-{uuid.uuid4().hex[:6]}.com")
                session.add_all([org_a, org_b])
                await session.commit()
                real_org_a_id = org_a.id
                real_org_b_id = org_b.id

            # Unauthenticated requests must be rejected.
            for path, body in (
                ("/api/v1/tenants/partition-keys", {"key": "cache_item", "event_type": "project.updated", "channel": "live_feed", "priority": "high"}),
                ("/api/v1/tenants/validate-vector-query", {"query_filter": {"author": "alice"}}),
                ("/api/v1/tenants/audit-access", {"target_tenant_id": str(real_org_b_id)}),
            ):
                res = await client.post(path, json=body)
                assert res.status_code in (401, 403), f"Expected 401/403 for unauthenticated {path}, got {res.status_code}: {res.text}"
            print("SUCCESS: All three endpoints correctly reject unauthenticated requests.")

            dev_headers = await create_authenticated_headers(client, real_org_a_id)

            # POST /api/v1/tenants/partition-keys -- tenant_id derived server-side from the caller.
            res_part = await client.post(
                "/api/v1/tenants/partition-keys",
                json={"key": "cache_item", "event_type": "project.updated", "channel": "live_feed", "priority": "high"},
                headers=dev_headers,
            )
            assert res_part.status_code == 200, res_part.text
            assert res_part.json()["tenant_id"] == str(real_org_a_id)
            assert res_part.json()["redis_key"] == f"tenant:{real_org_a_id}:cache_item"

            # POST /api/v1/tenants/validate-vector-query
            res_vec = await client.post(
                "/api/v1/tenants/validate-vector-query",
                json={"query_filter": {"author": "alice"}},
                headers=dev_headers,
            )
            assert res_vec.status_code == 200, res_vec.text
            assert res_vec.json()["enforced_vector_filter"]["tenant_id"] == str(real_org_a_id)

            # POST /api/v1/tenants/audit-access -- a non-super-admin caller cannot get
            # allowed:true for a cross-tenant audit even by claiming is_super_admin in the body
            # (the endpoint no longer accepts that field at all).
            res_aud_denied = await client.post(
                "/api/v1/tenants/audit-access",
                json={"target_tenant_id": str(real_org_b_id), "is_super_admin": True},
                headers=dev_headers,
            )
            assert res_aud_denied.status_code == 403, res_aud_denied.text
            print("SUCCESS: Non-super-admin caller denied cross-tenant audit-access even when claiming is_super_admin in the body.")

            # A real SuperAdmin-role caller (role read from the database, not the request body)
            # must be permitted the same cross-tenant audit.
            async with SessionLocal() as session:
                super_admin_role = (await session.execute(select(Role).where(Role.name == "SuperAdmin"))).scalar_one()
                admin_email = f"tiso-admin-{uuid.uuid4().hex[:8]}@example.com"
                admin_user = User(
                    organization_id=real_org_a_id,
                    email=admin_email,
                    full_name="Tenant Iso Admin",
                    hashed_password=get_password_hash("TestPass123!")
                )
                admin_user.roles.append(super_admin_role)
                session.add(admin_user)
                await session.commit()
                await session.refresh(admin_user)
                admin_user_id = admin_user.id

            res_login = await client.post("/api/v1/auth/login", json={"email": admin_email, "password": "TestPass123!"})
            assert res_login.status_code == 200, res_login.text
            admin_headers = {"Authorization": f"Bearer {res_login.json()['access_token']}"}

            res_aud_ok = await client.post(
                "/api/v1/tenants/audit-access",
                json={"target_tenant_id": str(real_org_b_id)},
                headers=admin_headers,
            )
            assert res_aud_ok.status_code == 200, res_aud_ok.text
            assert res_aud_ok.json()["allowed"] is True

            print("SUCCESS: Multi-Tenant Isolation REST API endpoints verified -- real auth required, tenant_id and is_super_admin both derived server-side.")
        finally:
            async with SessionLocal() as session:
                for uid in [u for u in [admin_user_id] if u]:
                    u = await session.get(User, uid)
                    if u:
                        await session.delete(u)
                await session.commit()

                for org_id in [real_org_a_id, real_org_b_id]:
                    if not org_id:
                        continue
                    user_res = await session.execute(select(User).where(User.organization_id == org_id))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    org_row = await session.get(Organization, org_id)
                    if org_row:
                        await session.delete(org_row)
                await session.commit()

    print("\nAll Multi-Tenant Schema & Virtual Isolation Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_tenant_isolation_flow())
