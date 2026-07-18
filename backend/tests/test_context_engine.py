import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization
from app.models.context import ContextChunk, ContextEmbedding
from app.context.chunker import TextChunker
from app.context.embeddings import get_embedding_generator
from app.services.context import ContextEngineService
from app.db.session import SessionLocal

async def test_context_engine_flow():
    print("Initializing Context Engine validation tests...")

    # 1. Test TextChunker
    print("\nTest 1: Testing TextChunker sentence/paragraph splitting...")
    chunker = TextChunker(default_chunk_size=20, default_overlap=5)
    sample_text = (
        "FastAPI is a modern web framework for Python.\n\n"
        "SQLAlchemy provides powerful ORM and async database capabilities.\n\n"
        "PostgreSQL vector search enables semantic context retrieval for multi-agent workflows."
    )
    chunks = chunker.chunk_text(sample_text)
    assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"
    assert "FastAPI" in chunks[0]["content"]
    print(f"SUCCESS: TextChunker produced {len(chunks)} chunks.")

    # 2. Test Embedding Generator
    print("\nTest 2: Testing Embedding Generator vector dimensions...")
    generator = get_embedding_generator()
    vec = await generator.generate_embedding("Refactoring Auth service")
    assert len(vec) == 1536, f"Expected 1536-dim vector, got {len(vec)}"
    print("SUCCESS: Embedding generator returned 1536-dimensional float vector.")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    created_chunk_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization
            async with SessionLocal() as session:
                print("\nInserting test organization database entry...")
                org = Organization(name=f"Context Test Org {suffix}", domain=f"context-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            source_id = uuid.uuid4()
            doc_text = (
                "Feature Request: Implement OAuth2 JWT authentication for frontend users.\n"
                "The backend must issue 15-minute access tokens and 7-day refresh tokens.\n"
                "All user endpoints should validate bearer tokens against the user database repository."
            )

            # 3. Test Direct ContextEngineService Document Indexing
            print("\nTest 3: Testing ContextEngineService direct indexing...")
            async with SessionLocal() as session:
                service = ContextEngineService(session)
                indexed_chunks = await service.index_document(
                    organization_id=test_org_id,
                    source_type="feature_spec",
                    source_id=source_id,
                    text=doc_text,
                    metadata={"author": "alice", "priority": "high"}
                )
                assert len(indexed_chunks) > 0
                for c in indexed_chunks:
                    created_chunk_ids.append(c.id)
                print(f"SUCCESS: Direct indexing persisted {len(indexed_chunks)} ContextChunk records.")

            # 4. Test Semantic Context Search
            print("\nTest 4: Testing ContextEngineService semantic vector search...")
            async with SessionLocal() as session:
                service = ContextEngineService(session)
                search_results = await service.search_context(
                    organization_id=test_org_id,
                    query_text="JWT authentication refresh tokens",
                    top_k=3
                )
                assert len(search_results) > 0
                top_result = search_results[0]
                assert top_result["source_type"] == "feature_spec"
                assert top_result["score"] > 0.0
                print(f"SUCCESS: Semantic search returned top match with score={top_result['score']:.4f}.")

            # 5. Test HTTP API Endpoint: POST /api/v1/context/index
            print("\nTest 5: Requesting POST /api/v1/context/index...")
            api_source_id = str(uuid.uuid4())
            res = await client.post(
                "/api/v1/context/index",
                json={
                    "organization_id": str(test_org_id),
                    "source_type": "pull_request",
                    "source_id": api_source_id,
                    "text": "PR #42: Fixed database session transaction deadlock in Outbox worker loop.",
                    "metadata": {"repo": "ai-tpm-backend"}
                }
            )
            assert res.status_code == 201, f"Endpoint failed: {res.text}"
            res_json = res.json()
            assert res_json["status"] == "indexed"
            for cid in res_json["chunk_ids"]:
                created_chunk_ids.append(uuid.UUID(cid))
            print(f"SUCCESS: HTTP index endpoint returned {res_json['chunks_indexed']} chunks.")

            # 6. Test HTTP API Endpoint: POST /api/v1/context/search
            print("\nTest 6: Requesting POST /api/v1/context/search...")
            res = await client.post(
                "/api/v1/context/search",
                json={
                    "organization_id": str(test_org_id),
                    "query": "outbox transaction deadlock",
                    "top_k": 5
                }
            )
            assert res.status_code == 200, f"Search failed: {res.text}"
            search_json = res.json()
            assert search_json["results_count"] > 0
            print(f"SUCCESS: HTTP search endpoint returned {search_json['results_count']} semantic matches.")

        finally:
            # Clean up database records
            print("\nCleaning up context engine test database entries...")
            async with SessionLocal() as session:
                for cid in created_chunk_ids:
                    # Delete ContextEmbedding first (foreign key constraint)
                    res = await session.execute(select(ContextEmbedding).where(ContextEmbedding.chunk_id == cid))
                    emb = res.scalar_one_or_none()
                    if emb:
                        await session.delete(emb)
                    res = await session.execute(select(ContextChunk).where(ContextChunk.id == cid))
                    chk = res.scalar_one_or_none()
                    if chk:
                        await session.delete(chk)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Context Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_context_engine_flow())
