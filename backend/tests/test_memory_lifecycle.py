import asyncio
import time
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.models.tenant import Organization
from app.db.session import SessionLocal
from app.services.memory_lifecycle import (
    get_memory_lifecycle_engine,
    MemoryLifecycleEngine
)
from tests._auth_helpers import create_authenticated_headers

async def test_memory_lifecycle_flow():
    print("Initializing Memory Lifecycle & Automated Vector GC validation tests...")
    engine = get_memory_lifecycle_engine()
    org_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())

    # 1. Test Conversation Compression Pipeline
    print("\nTest 1: Testing Memory Compression Pipeline (threshold >= 10 messages)...")
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message payload #{i} discussing sprint architecture."}
        for i in range(12)
    ]

    comp_res = engine.compress_conversation_history(org_id, conv_id, messages, message_threshold=10)
    assert comp_res["compressed"] is True
    assert comp_res["messages_summarized"] == 4 # 30% of 12 = 4 messages summarized
    assert comp_res["messages_retained"] == 8   # 70% retained
    assert "vector_memory_id" in comp_res
    print("SUCCESS: Conversation compressed, older 30% summarized and indexed into pgvector.")

    # 2. Test Garbage Collection & Partition Rotator (> 90 days archiving, > 1 hr short-term TTL purge)
    print("\nTest 2: Testing Garbage Collection & Cold Storage Partition Rotator...")
    now = time.time()
    records = [
        # Expired short-term memory (2 hours old) -> Purge
        {"id": "st-1", "memory_type": "short_term", "content": "Transient state", "created_at": now - 7200},
        # Valid short-term memory (10 mins old) -> Retain
        {"id": "st-2", "memory_type": "short_term", "content": "Active state", "created_at": now - 600},
        # Historical conversation log (100 days old) -> Archive to Cold Storage
        {"id": "hist-1", "memory_type": "historical_log", "content": "Sprint review 2025", "created_at": now - (100 * 86400)},
        # Recent conversation log (10 days old) -> Retain
        {"id": "hist-2", "memory_type": "historical_log", "content": "Sprint review 2026", "created_at": now - (10 * 86400)}
    ]

    gc_res = engine.run_garbage_collection(org_id, records, retention_days=90)
    assert gc_res["total_evaluated"] == 4
    assert gc_res["purged_short_term_ttl"] == 1
    assert gc_res["archived_to_cold_storage"] == 1
    assert gc_res["retained_active_records"] == 2
    print("SUCCESS: Expired short-term records purged and > 90-day records archived to cold storage.")

    # 3. Test HNSW Vector Index Rebuild Trigger
    print("\nTest 3: Testing HNSW vector index maintenance sweep...")
    rebuild_res = engine.trigger_hnsw_index_rebuild(org_id)
    assert rebuild_res["status"] == "COMPLETED"
    assert rebuild_res["index_type"] == "HNSW"
    print("SUCCESS: Vector HNSW index rebuild sweep executed.")

    # 4. Test HTTP REST API Endpoints require real authentication (Phase 83) -- and that
    #    organization_id is derived from the authenticated caller, never client-supplied.
    print("\nTest 4: Testing Memory Lifecycle HTTP REST API endpoints require real authentication...")
    real_org_id = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org = Organization(name=f"Mem Lifecycle Org {uuid.uuid4().hex[:6]}", domain=f"memlc-{uuid.uuid4().hex[:6]}.com")
                session.add(org)
                await session.commit()
                real_org_id = org.id

            # Unauthenticated requests must be rejected, not silently accepted (Phase 83).
            for path, body in (
                ("/api/v1/memory-lifecycle/compress", {"conversation_id": conv_id, "messages": messages, "message_threshold": 10}),
                ("/api/v1/memory-lifecycle/gc", {"memory_records": records, "retention_days": 90}),
                ("/api/v1/memory-lifecycle/rebuild-index", {}),
            ):
                res = await client.post(path, json=body)
                assert res.status_code in (401, 403), f"Expected 401/403 for unauthenticated {path}, got {res.status_code}: {res.text}"
            print("SUCCESS: All three endpoints correctly reject unauthenticated requests.")

            auth_headers = await create_authenticated_headers(client, real_org_id)

            # POST /api/v1/memory-lifecycle/compress -- no organization_id in the body anymore;
            # it's derived from the real authenticated caller server-side.
            res_comp = await client.post(
                "/api/v1/memory-lifecycle/compress",
                json={"conversation_id": conv_id, "messages": messages, "message_threshold": 10},
                headers=auth_headers,
            )
            assert res_comp.status_code == 200, res_comp.text
            assert res_comp.json()["compressed"] is True

            # POST /api/v1/memory-lifecycle/gc
            res_gc = await client.post(
                "/api/v1/memory-lifecycle/gc",
                json={"memory_records": records, "retention_days": 90},
                headers=auth_headers,
            )
            assert res_gc.status_code == 200, res_gc.text
            assert res_gc.json()["archived_to_cold_storage"] == 1

            # POST /api/v1/memory-lifecycle/rebuild-index
            res_reb = await client.post(
                "/api/v1/memory-lifecycle/rebuild-index",
                json={},
                headers=auth_headers,
            )
            assert res_reb.status_code == 200, res_reb.text
            assert res_reb.json()["status"] == "COMPLETED"

            print("SUCCESS: Memory Lifecycle REST API endpoints correctly require real authentication and derive organization_id server-side.")
        finally:
            if real_org_id:
                async with SessionLocal() as session:
                    from app.models.tenant import User
                    user_res = await session.execute(select(User).where(User.organization_id == real_org_id))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    org_row = await session.get(Organization, real_org_id)
                    if org_row:
                        await session.delete(org_row)
                    await session.commit()

    print("\nAll Memory Lifecycle & Automated Vector GC System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_memory_lifecycle_flow())
