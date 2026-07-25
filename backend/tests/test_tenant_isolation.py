import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.tenant_isolation import (
    get_tenant_isolation_engine,
    TenantIsolationEngine
)

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

    # 4. Test REST API Endpoints
    print("\nTest 4: Testing Tenant Isolation HTTP REST API endpoints...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST /api/v1/tenants/partition-keys
        res_part = await client.post(
            "/api/v1/tenants/partition-keys",
            json={
                "tenant_id": tenant_a,
                "key": "cache_item",
                "event_type": "project.updated",
                "channel": "live_feed",
                "priority": "high"
            }
        )
        assert res_part.status_code == 200
        assert res_part.json()["redis_key"].startswith("tenant:")

        # POST /api/v1/tenants/validate-vector-query
        res_vec = await client.post(
            "/api/v1/tenants/validate-vector-query",
            json={"tenant_id": tenant_a, "query_filter": {"author": "alice"}}
        )
        assert res_vec.status_code == 200
        assert res_vec.json()["enforced_vector_filter"]["tenant_id"] == tenant_a

        # POST /api/v1/tenants/audit-access (Unauthorized cross-tenant -> 403)
        res_aud_denied = await client.post(
            "/api/v1/tenants/audit-access",
            json={"source_tenant_id": tenant_a, "target_tenant_id": tenant_b, "is_super_admin": False}
        )
        assert res_aud_denied.status_code == 403

        # POST /api/v1/tenants/audit-access (Super admin -> 200)
        res_aud_ok = await client.post(
            "/api/v1/tenants/audit-access",
            json={"source_tenant_id": tenant_a, "target_tenant_id": tenant_b, "is_super_admin": True}
        )
        assert res_aud_ok.status_code == 200

        print("SUCCESS: Multi-Tenant Isolation REST API endpoints verified.")

    print("\nAll Multi-Tenant Schema & Virtual Isolation Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_tenant_isolation_flow())
