import asyncio
import uuid
import json
from unittest.mock import patch
from sqlalchemy import select

import app.db.base  # Register models
from app.models.tenant import Organization
from app.models.context import ContextChunk, ContextEmbedding
from app.agents.base import BaseAgent
from app.services.context import ContextEngineService
from app.tools.context_tools import ContextSearchTool
from app.db.session import SessionLocal


async def test_search_reranking_flow():
    print("Initializing Real Search Reranking (Phase 78) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_id = None
    created_chunk_ids = []
    llm_call_count = {"n": 0}

    try:
        async with SessionLocal() as session:
            org = Organization(name=f"Rerank Org {suffix}", domain=f"rerank-{suffix}.com")
            session.add(org)
            await session.commit()
            org_id = org.id

        # Index 4 real, distinctly-worded chunks to search against. The mock embedding
        # generator used in this sandboxed environment (no OPENAI_API_KEY) hashes text
        # deterministically but not semantically, so this test never assumes which specific
        # chunk ranks where by vector similarity -- only that reranking correctly reorders
        # whatever real candidate list comes back, which is the actual mechanism under test.
        async with SessionLocal() as session:
            service = ContextEngineService(session)
            texts = [
                f"Deploying the {suffix} authentication service to production tonight.",
                f"The {suffix} billing dashboard shows a rendering bug on Safari.",
                f"Root cause of the {suffix} login race condition has been identified.",
                f"Weekly standup notes for the {suffix} mobile app team.",
            ]
            for i, text in enumerate(texts):
                chunks = await service.index_document(
                    organization_id=org_id, source_type="doc",
                    source_id=uuid.uuid5(uuid.NAMESPACE_URL, f"rerank-{suffix}-{i}"),
                    text=text,
                )
                created_chunk_ids.extend(c.id for c in chunks)
        print(f"Test org created and 4 real chunks indexed. Org={org_id}")

        # Establish the real, un-reranked vector-similarity baseline order.
        async with SessionLocal() as session:
            service = ContextEngineService(session)
            baseline = await service.search_context(organization_id=org_id, query_text="login issue", top_k=4)
        baseline_ids = [r["chunk_id"] for r in baseline]
        assert len(baseline_ids) == 4

        async def fake_llm_call_reverse(self, prompt, system_prompt, task_category="output_reflection"):
            llm_call_count["n"] += 1
            return json.dumps(list(range(len(baseline_ids)))[::-1])

        async def fake_llm_call_failing(self, prompt, system_prompt, task_category="output_reflection"):
            llm_call_count["n"] += 1
            raise RuntimeError("Simulated LLM provider failure")

        async def fake_llm_call_bad_indices(self, prompt, system_prompt, task_category="output_reflection"):
            llm_call_count["n"] += 1
            # 99 is out of range, 1 is a duplicate -- both must be filtered, not crash.
            return json.dumps([99, 1, 1, 0])

        # 1. rerank=False (default): unchanged behavior, no LLM call made.
        print("\nTest 1: Verifying rerank=False makes no LLM call and returns the default vector order...")
        llm_call_count["n"] = 0
        with patch.object(BaseAgent, "_llm_call", new=fake_llm_call_reverse):
            async with SessionLocal() as session:
                service = ContextEngineService(session)
                default_results = await service.search_context(organization_id=org_id, query_text="login issue", top_k=4)
        assert llm_call_count["n"] == 0, "rerank=False must never call the LLM"
        assert [r["chunk_id"] for r in default_results] == baseline_ids
        print("SUCCESS: rerank=False made zero LLM calls, behavior unchanged from the real baseline.")

        # 2. rerank=True with a real (mocked) LLM response reorders results exactly as the
        #    reranker specified -- proves the mechanism, not any assumption about which
        #    content is "most relevant" under a non-semantic mock embedding.
        print("\nTest 2: Verifying rerank=True reorders results exactly per the real (mocked) LLM response...")
        llm_call_count["n"] = 0
        with patch.object(BaseAgent, "_llm_call", new=fake_llm_call_reverse):
            async with SessionLocal() as session:
                service = ContextEngineService(session)
                reranked_results = await service.search_context(organization_id=org_id, query_text="login issue", top_k=4, rerank=True)
        assert llm_call_count["n"] == 1, "rerank=True must call the LLM exactly once"
        assert [r["chunk_id"] for r in reranked_results] == baseline_ids[::-1], "Reranked order must exactly match the real reranker response"
        print("SUCCESS: rerank=True correctly reordered results exactly per the real reranker response.")

        # 3. rerank=True with a failing LLM falls back to the original vector-similarity order.
        print("\nTest 3: Verifying a failing reranker call falls back to the original vector order...")
        llm_call_count["n"] = 0
        with patch.object(BaseAgent, "_llm_call", new=fake_llm_call_failing):
            async with SessionLocal() as session:
                service = ContextEngineService(session)
                fallback_results = await service.search_context(organization_id=org_id, query_text="login issue", top_k=2, rerank=True)
        assert llm_call_count["n"] == 1
        assert [r["chunk_id"] for r in fallback_results] == baseline_ids[:2], "A failed rerank must fall back to the real, un-reranked top_k"
        print("SUCCESS: Failed reranker call correctly fell back to the real, un-reranked vector order.")

        # 4. rerank=True with out-of-range/duplicate indices are filtered, not corrupting results.
        print("\nTest 4: Verifying out-of-range/duplicate reranker indices are filtered safely...")
        llm_call_count["n"] = 0
        with patch.object(BaseAgent, "_llm_call", new=fake_llm_call_bad_indices):
            async with SessionLocal() as session:
                service = ContextEngineService(session)
                filtered_results = await service.search_context(organization_id=org_id, query_text="login issue", top_k=3, rerank=True)
        assert [r["chunk_id"] for r in filtered_results] == [baseline_ids[1], baseline_ids[0]], \
            f"Expected only the 2 valid, de-duplicated indices (1, 0) to survive, got: {filtered_results}"
        print("SUCCESS: Invalid reranker indices were correctly filtered without corrupting the result list.")

        # 5. ContextSearchTool calls search_context with rerank=True end-to-end.
        print("\nTest 5: Verifying ContextSearchTool uses real reranking end-to-end...")
        llm_call_count["n"] = 0
        with patch.object(BaseAgent, "_llm_call", new=fake_llm_call_reverse):
            async with SessionLocal() as session:
                tool_result = await ContextSearchTool().execute(
                    {"organization_id": str(org_id), "query": "login issue", "top_k": 4}, session=session,
                )
        assert tool_result["status"] == "success"
        assert llm_call_count["n"] == 1, "ContextSearchTool must trigger a real reranking call"
        assert [r["chunk_id"] for r in tool_result["results"]] == baseline_ids[::-1]
        print("SUCCESS: ContextSearchTool correctly triggered real reranking end-to-end.")

    finally:
        print("\nCleaning up test database entries...")
        async with SessionLocal() as session:
            for cid in created_chunk_ids:
                res = await session.execute(select(ContextEmbedding).where(ContextEmbedding.chunk_id == cid))
                for emb in res.scalars().all():
                    await session.delete(emb)
                res = await session.execute(select(ContextChunk).where(ContextChunk.id == cid))
                chk = res.scalar_one_or_none()
                if chk:
                    await session.delete(chk)
            await session.flush()
            if org_id:
                org_row = await session.get(Organization, org_id)
                if org_row:
                    await session.delete(org_row)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Real Search Reranking tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_search_reranking_flow())
