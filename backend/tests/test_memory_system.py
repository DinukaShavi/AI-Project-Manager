import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization
from app.models.memory import AgentMemory
from app.memory.manager import get_memory_manager
from app.services.memory import MemoryService
from app.db.session import SessionLocal

async def test_memory_system_flow():
    print("Initializing Memory System validation tests...")

    # 1. Test In-Memory Working Memory Manager
    print("\nTest 1: Testing in-memory Working Memory Manager...")
    mem_mgr = get_memory_manager()
    session_id = "session-101"
    mem_mgr.set_working_memory(session_id, "current_task", "Refactor Auth service")
    mem_mgr.set_working_memory(session_id, "step_count", 3)

    assert mem_mgr.get_working_memory(session_id, "current_task") == "Refactor Auth service"
    assert mem_mgr.get_working_memory(session_id, "step_count") == 3

    mem_mgr.clear_working_memory(session_id)
    assert mem_mgr.get_working_memory(session_id, "current_task") is None
    print("SUCCESS: In-memory working memory manager verified.")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    created_memory_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization
            async with SessionLocal() as session:
                print("\nInserting test organization database entry...")
                org = Organization(name=f"Memory Test Org {suffix}", domain=f"mem-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            # 2. Test MemoryService Direct Persistence & Recall
            print("\nTest 2: Testing MemoryService direct persistence & entity recall...")
            async with SessionLocal() as session:
                service = MemoryService(session)
                entity_mem = await service.store_memory(
                    organization_id=test_org_id,
                    memory_type="entity",
                    key="tech_stack_facts",
                    value_json={"framework": "FastAPI", "database": "PostgreSQL"},
                    agent_type="architect"
                )
                created_memory_ids.append(entity_mem.id)
                assert entity_mem.key == "tech_stack_facts"
                print(f"SUCCESS: Entity memory stored in DB. ID: {entity_mem.id}")

                recalled = await service.recall_memory(test_org_id, "tech_stack_facts")
                assert recalled is not None
                assert recalled.value_json["framework"] == "FastAPI"
                print("SUCCESS: Entity memory recalled by key.")

            # 3. Test Long-Term Vector Memory Semantic Search
            print("\nTest 3: Testing long-term vector memory semantic search...")
            async with SessionLocal() as session:
                service = MemoryService(session)
                lt_mem = await service.store_memory(
                    organization_id=test_org_id,
                    memory_type="long_term",
                    key="sprint_14_retrospective",
                    content="Decided to adopt Outbox Pattern and InMemoryEventBus for offline unit testing.",
                    agent_type="tpm"
                )
                created_memory_ids.append(lt_mem.id)
                assert lt_mem.embedding is not None
                print("SUCCESS: Long-term vector memory stored with 1536-dim embedding.")

                search_res = await service.search_long_term_memory(
                    organization_id=test_org_id,
                    query_text="Outbox Pattern event bus testing",
                    limit=3
                )
                assert len(search_res) > 0
                top_hit = search_res[0]
                assert top_hit["key"] == "sprint_14_retrospective"
                assert isinstance(top_hit["score"], float)
                print(f"SUCCESS: Long-term memory search returned top hit with score={top_hit['score']:.4f}.")

            # 4. Test HTTP API Endpoint: POST /api/v1/memory
            print("\nTest 4: Requesting POST /api/v1/memory...")
            res = await client.post(
                "/api/v1/memory",
                json={
                    "organization_id": str(test_org_id),
                    "memory_type": "entity",
                    "key": "dev_velocity_fact",
                    "value_json": {"avg_story_points": 18},
                    "agent_type": "tpm"
                }
            )
            assert res.status_code == 201, f"Endpoint failed: {res.text}"
            mem_json = res.json()
            created_memory_ids.append(uuid.UUID(mem_json["memory_id"]))
            print(f"SUCCESS: Memory stored via HTTP API. ID: {mem_json['memory_id']}")

            # 5. Test HTTP API Endpoint: GET /api/v1/memory
            print("\nTest 5: Requesting GET /api/v1/memory...")
            res = await client.get(f"/api/v1/memory?organization_id={test_org_id}&key=dev_velocity_fact")
            assert res.status_code == 200, f"Recall failed: {res.text}"
            rec_json = res.json()
            assert rec_json["key"] == "dev_velocity_fact"
            assert rec_json["value_json"]["avg_story_points"] == 18
            print("SUCCESS: Memory recalled via HTTP API.")

            # 6. Test HTTP API Endpoint: POST /api/v1/memory/search
            print("\nTest 6: Requesting POST /api/v1/memory/search...")
            res = await client.post(
                "/api/v1/memory/search",
                json={
                    "organization_id": str(test_org_id),
                    "query": "Outbox pattern decisions",
                    "limit": 3
                }
            )
            assert res.status_code == 200
            s_json = res.json()
            assert s_json["results_count"] > 0
            print(f"SUCCESS: Memory search via HTTP API returned {s_json['results_count']} results.")

        finally:
            # Clean up database records
            print("\nCleaning up memory system test database entries...")
            async with SessionLocal() as session:
                for mid in created_memory_ids:
                    res = await session.execute(select(AgentMemory).where(AgentMemory.id == mid))
                    m = res.scalar_one_or_none()
                    if m:
                        await session.delete(m)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Memory System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_memory_system_flow())
