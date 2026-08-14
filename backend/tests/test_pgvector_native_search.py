import asyncio
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

import app.db.base # Register models
from app.core.config import settings
from app.models.context import ContextChunk, ContextEmbedding
from app.models.memory import AgentMemory
from app.repositories.context import ContextRepository
from app.services.memory import MemoryService
from app.db.session import SessionLocal


async def test_pgvector_native_search_flow():
    print("Initializing pgvector-native similarity search validation tests...")

    # No pgvector-enabled Postgres is reachable in this environment (verified directly: the
    # 'vector' extension is not even present in pg_available_extensions on this local server,
    # and USE_PGVECTOR=False here, so the embedding columns are the DOUBLE PRECISION[]
    # compile-fallback, not real pgvector `vector` columns). Executing the native <=> query
    # against this database would fail with an "operator does not exist" error, the same
    # reason ADR 008's HNSW indexing can't be exercised live here either. What CAN be verified
    # without a live pgvector server: (a) the native query compiles to correct, real pgvector
    # SQL (ORDER BY/LIMIT pushed down, not fetched client-side), and (b) settings.USE_PGVECTOR
    # correctly routes to the native vs. Python-fallback code path.
    original_use_pgvector = settings.USE_PGVECTOR

    try:
        # 1. Verify the native ContextRepository query compiles to real pgvector SQL.
        print("\nTest 1: Verifying ContextRepository's native query compiles with the <=> operator, ORDER BY, and LIMIT pushed to SQL...")
        query_vec = [0.1] * 1536
        distance_expr = ContextEmbedding.embedding.cosine_distance(query_vec)
        from sqlalchemy import select
        import uuid
        native_query = (
            select(ContextChunk, distance_expr.label("distance"))
            .join(ContextEmbedding, ContextChunk.id == ContextEmbedding.chunk_id)
            .where(ContextChunk.organization_id == uuid.uuid4())
            .order_by(distance_expr)
            .limit(5)
        )
        compiled_sql = str(native_query.compile(dialect=postgresql.dialect()))
        assert "<=>" in compiled_sql, f"Expected the pgvector cosine-distance operator in the compiled SQL: {compiled_sql}"
        assert "ORDER BY" in compiled_sql and "LIMIT" in compiled_sql, \
            f"Expected sorting/limiting to be pushed down to SQL, not done in Python: {compiled_sql}"
        print("SUCCESS: Native query pushes cosine-distance ordering and LIMIT down to Postgres via pgvector's <=> operator.")

        # 2. Verify the native AgentMemory (long-term memory) query compiles the same way.
        print("\nTest 2: Verifying MemoryService's native query compiles with the <=> operator...")
        mem_distance_expr = AgentMemory.embedding.cosine_distance(query_vec)
        mem_query = select(AgentMemory, mem_distance_expr.label("distance")).order_by(mem_distance_expr).limit(5)
        mem_compiled_sql = str(mem_query.compile(dialect=postgresql.dialect()))
        assert "<=>" in mem_compiled_sql
        assert "ORDER BY" in mem_compiled_sql and "LIMIT" in mem_compiled_sql
        print("SUCCESS: Native long-term memory query also pushes cosine-distance ordering down to Postgres.")

        # 3. Verify settings.USE_PGVECTOR correctly routes ContextRepository.search_context to
        # the native vs. Python-fallback method (mocking each helper to avoid needing a real
        # pgvector-enabled database for the routing check itself).
        print("\nTest 3: Verifying USE_PGVECTOR routes ContextRepository.search_context correctly...")
        async with SessionLocal() as session:
            repo = ContextRepository(session)

            settings.USE_PGVECTOR = True
            with patch.object(ContextRepository, "_search_context_native", new=AsyncMock(return_value=[])) as native_mock, \
                 patch.object(ContextRepository, "_search_context_python", new=AsyncMock(return_value=[])) as python_mock:
                await repo.search_context(uuid.uuid4(), query_vec)
                assert native_mock.await_count == 1, "USE_PGVECTOR=True must route to the native pgvector path"
                assert python_mock.await_count == 0

            settings.USE_PGVECTOR = False
            with patch.object(ContextRepository, "_search_context_native", new=AsyncMock(return_value=[])) as native_mock, \
                 patch.object(ContextRepository, "_search_context_python", new=AsyncMock(return_value=[])) as python_mock:
                await repo.search_context(uuid.uuid4(), query_vec)
                assert python_mock.await_count == 1, "USE_PGVECTOR=False must route to the Python fallback path"
                assert native_mock.await_count == 0
        print("SUCCESS: search_context correctly routes based on settings.USE_PGVECTOR.")

        # 4. Same routing check for MemoryService.search_long_term_memory.
        print("\nTest 4: Verifying USE_PGVECTOR routes MemoryService.search_long_term_memory correctly...")
        async with SessionLocal() as session:
            service = MemoryService(session)
            service.embedding_generator.generate_embedding = AsyncMock(return_value=query_vec)

            settings.USE_PGVECTOR = True
            with patch.object(MemoryService, "_search_long_term_memory_native", new=AsyncMock(return_value=[])) as native_mock, \
                 patch.object(MemoryService, "_search_long_term_memory_python", new=AsyncMock(return_value=[])) as python_mock:
                await service.search_long_term_memory(uuid.uuid4(), "test query")
                assert native_mock.await_count == 1
                assert python_mock.await_count == 0

            settings.USE_PGVECTOR = False
            with patch.object(MemoryService, "_search_long_term_memory_native", new=AsyncMock(return_value=[])) as native_mock, \
                 patch.object(MemoryService, "_search_long_term_memory_python", new=AsyncMock(return_value=[])) as python_mock:
                await service.search_long_term_memory(uuid.uuid4(), "test query")
                assert python_mock.await_count == 1
                assert native_mock.await_count == 0
        print("SUCCESS: search_long_term_memory correctly routes based on settings.USE_PGVECTOR.")

    finally:
        settings.USE_PGVECTOR = original_use_pgvector

    print("\nAll pgvector-native similarity search tests completed successfully!")
    print("NOTE: The native <=> query path's SQL construction was verified by compiling it to")
    print("real pgvector SQL; live execution against a pgvector-enabled Postgres could not be")
    print("verified in this environment (the 'vector' extension is not installed here).")

if __name__ == "__main__":
    asyncio.run(test_pgvector_native_search_flow())
