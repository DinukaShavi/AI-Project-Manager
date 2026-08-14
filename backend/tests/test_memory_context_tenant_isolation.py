import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User
from app.models.memory import AgentMemory
from app.models.context import ContextChunk, ContextEmbedding
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_memory_context_tenant_isolation_flow():
    print("Initializing Memory & Context Cross-Tenant Isolation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    created_memory_ids = []
    created_chunk_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"MemCtx Tenant Org A {suffix}", domain=f"mcio-a-{suffix}.com")
                org_b = Organization(name=f"MemCtx Tenant Org B {suffix}", domain=f"mcio-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.commit()
            org_a_id, org_b_id = org_a.id, org_b.id
            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs and authenticated users created. Org A={org_a_id} Org B={org_b_id}")

            # =====================================================================
            # MEMORY
            # =====================================================================

            # 1. Org A stores a real long-term memory via the authenticated HTTP flow.
            secret_key = f"secret-project-roadmap-{suffix}"
            secret_content = f"CONFIDENTIAL-ORGA-{suffix}: Q3 roadmap includes acquiring Northwind Traders."
            res = await client.post(
                "/api/v1/memory",
                json={
                    "memory_type": "long_term",
                    "key": secret_key,
                    "content": secret_content,
                    "agent_type": "tpm"
                },
                headers=headers_a,
            )
            assert res.status_code == 201, f"Memory store failed: {res.text}"
            memory_a_id = res.json()["memory_id"]
            created_memory_ids.append(uuid.UUID(memory_a_id))
            print(f"SUCCESS: Org A stored a real long-term memory. Memory ID: {memory_a_id}")

            # Verify the persisted row actually belongs to Org A (explicit ownership check,
            # not assumed).
            async with SessionLocal() as session:
                persisted = await session.get(AgentMemory, uuid.UUID(memory_a_id))
                assert persisted is not None
                assert persisted.organization_id == org_a_id

            # 2. Org A can recall its own memory by key.
            print("\nTest 2: Verifying Org A can recall its own memory...")
            res = await client.get(
                f"/api/v1/memory?key={secret_key}",
                headers=headers_a,
            )
            assert res.status_code == 200, res.text
            assert res.json()["content"] == secret_content
            print("SUCCESS: Org A recalled its own memory by key.")

            # 3. Org A can find it via long-term vector search.
            print("\nTest 3: Verifying Org A can search its own long-term memory...")
            res = await client.post(
                "/api/v1/memory/search",
                json={"query": "Q3 roadmap acquisition plans", "limit": 5},
                headers=headers_a,
            )
            assert res.status_code == 200, res.text
            search_json = res.json()
            assert any(r["memory_id"] == memory_a_id for r in search_json["results"])
            print("SUCCESS: Org A's search surfaced its own memory.")

            # 4. Org B cannot recall Org A's memory by key, even though `key` is a
            # non-tenant-scoped identifier -- organization_id must come from Org B's
            # authenticated identity, not any client input.
            print("\nTest 4: Verifying Org B cannot recall Org A's memory by key...")
            res = await client.get(
                f"/api/v1/memory?key={secret_key}",
                headers=headers_b,
            )
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            assert secret_content not in res.text
            assert secret_key not in res.text or "not found" in res.text.lower()
            print("SUCCESS: Org B correctly rejected (404) with no leaked memory data.")

            # 5. Org B's own long-term memory search never surfaces Org A's memory content,
            # even when Org B explicitly (and harmlessly) tries to supply Org A's real
            # organization_id in the request body -- the field isn't part of the documented
            # schema and must have zero effect; the authenticated org always wins.
            print("\nTest 5: Verifying Org B's search never surfaces Org A's memory content...")
            res = await client.post(
                "/api/v1/memory/search",
                json={
                    "query": "Q3 roadmap acquisition plans",
                    "limit": 25,
                    "organization_id": str(org_a_id),
                },
                headers=headers_b,
            )
            assert res.status_code == 200, res.text
            b_search_json = res.json()
            assert all(r["memory_id"] != memory_a_id for r in b_search_json["results"])
            raw_text = res.text
            assert secret_content not in raw_text
            assert memory_a_id not in raw_text
            print("SUCCESS: Org B's search returned zero results referencing Org A's memory.")

            # 6. Org B "creating" memory while attempting to pass Org A's organization_id
            # actually creates the row under Org B, not Org A (proving the field can't be
            # used to write into another tenant either).
            print("\nTest 6: Verifying a spoofed organization_id cannot redirect memory writes...")
            res = await client.post(
                "/api/v1/memory",
                json={
                    "memory_type": "short_term",
                    "key": f"spoof-attempt-{suffix}",
                    "content": "attempted cross-tenant write",
                    "organization_id": str(org_a_id),
                },
                headers=headers_b,
            )
            assert res.status_code == 201, res.text
            spoofed_id = uuid.UUID(res.json()["memory_id"])
            created_memory_ids.append(spoofed_id)
            async with SessionLocal() as session:
                spoofed_row = await session.get(AgentMemory, spoofed_id)
                assert spoofed_row.organization_id == org_b_id, "Memory must be owned by the authenticated org, never a client-supplied one"
            print("SUCCESS: Spoofed organization_id had no effect; memory was correctly written under Org B.")

            # 7. Org A's legitimate access still works (regression guard).
            print("\nTest 7: Verifying Org A retains full working access after the fix...")
            res = await client.get(f"/api/v1/memory?key={secret_key}", headers=headers_a)
            assert res.status_code == 200
            print("SUCCESS: Org A retains full working access to its own memory.")

            # =====================================================================
            # CONTEXT ENGINE
            # =====================================================================

            source_id_a = uuid.uuid4()
            context_secret = f"CONFIDENTIAL-ORGA-CONTEXT-{suffix}: internal migration runbook for the payments ledger."
            res = await client.post(
                "/api/v1/context/index",
                json={
                    "source_type": "doc",
                    "source_id": str(source_id_a),
                    "text": context_secret,
                },
                headers=headers_a,
            )
            assert res.status_code == 201, f"Context index failed: {res.text}"
            for cid in res.json()["chunk_ids"]:
                created_chunk_ids.append(uuid.UUID(cid))
            print(f"SUCCESS: Org A indexed real context content. Chunks: {res.json()['chunks_indexed']}")

            # 8. Org A can search its own context via the direct API.
            print("\nTest 8: Verifying Org A can search its own context via the direct API...")
            res = await client.post(
                "/api/v1/context/search",
                json={"query": "payments ledger migration runbook", "top_k": 5},
                headers=headers_a,
            )
            assert res.status_code == 200, res.text
            a_ctx_results = res.json()["results"]
            assert any(context_secret in r["content"] for r in a_ctx_results)
            print("SUCCESS: Org A's direct API context search surfaced its own content.")

            # 9. Org B's direct API context search, even supplying Org A's real
            # organization_id in the request body, never surfaces Org A's content -- the
            # direct REST endpoint already derives the tenant from current_user only.
            print("\nTest 9: Verifying Org B's direct API context search cannot see Org A's content...")
            res = await client.post(
                "/api/v1/context/search",
                json={
                    "query": "payments ledger migration runbook",
                    "top_k": 25,
                    "organization_id": str(org_a_id),
                },
                headers=headers_b,
            )
            assert res.status_code == 200, res.text
            raw_text = res.text
            assert context_secret not in raw_text
            assert str(source_id_a) not in raw_text
            print("SUCCESS: Org B's direct API context search returned no Org A content.")

            # 10. THE ACTUAL VULNERABILITY (pre-fix): the context_search *tool*, reachable
            # via POST /api/v1/tools/execute, accepted "organization_id" as a raw tool-call
            # parameter and used it verbatim to scope the vector search -- completely
            # bypassing the tenant boundary that the direct /context/search endpoint already
            # enforced. Org B invokes the tool while explicitly supplying Org A's real
            # organization_id; this must now be silently overridden with Org B's authenticated
            # organization_id (ToolExecutor.execute_tool), not honored.
            print("\nTest 10: Verifying the context_search TOOL cannot be used to read Org A's context via a spoofed organization_id...")
            res = await client.post(
                "/api/v1/tools/execute",
                json={
                    "tool_name": "context_search",
                    "parameters": {
                        "organization_id": str(org_a_id),
                        "query": "payments ledger migration runbook",
                        "top_k": 25,
                    },
                },
                headers=headers_b,
            )
            assert res.status_code == 200, f"Tool execution failed: {res.text}"
            tool_json = res.json()
            assert tool_json["status"] == "success"
            raw_text = res.text
            assert context_secret not in raw_text, "Tool execution leaked Org A's confidential context content to Org B"
            assert str(source_id_a) not in raw_text, "Tool execution leaked Org A's source_id to Org B"
            tool_results = tool_json["output"]["results"]
            assert len(tool_results) == 0, f"Expected zero cross-tenant results via the tool path, got: {tool_results}"
            print("SUCCESS: context_search tool call with a spoofed organization_id was safely overridden -- zero Org A results leaked.")

            # 11. Org A can still legitimately use the SAME tool to search its own context
            # (regression guard -- the override must not break same-tenant tool usage).
            print("\nTest 11: Verifying Org A can still use the context_search tool for its own data...")
            res = await client.post(
                "/api/v1/tools/execute",
                json={
                    "tool_name": "context_search",
                    "parameters": {
                        "organization_id": str(org_a_id),
                        "query": "payments ledger migration runbook",
                        "top_k": 5,
                    },
                },
                headers=headers_a,
            )
            assert res.status_code == 200, res.text
            a_tool_results = res.json()["output"]["results"]
            assert any(context_secret in r["content"] for r in a_tool_results)
            print("SUCCESS: Org A's own context_search tool call still works correctly.")

            # 12. Org A's direct context search still works after everything above
            # (final regression guard).
            print("\nTest 12: Verifying Org A's direct API context search still works...")
            res = await client.post(
                "/api/v1/context/search",
                json={"query": "payments ledger migration runbook", "top_k": 5},
                headers=headers_a,
            )
            assert res.status_code == 200
            assert any(context_secret in r["content"] for r in res.json()["results"])
            print("SUCCESS: Org A retains full working access to its own context.")

        finally:
            print("\nCleaning up memory/context tenant isolation test database entries...")
            async with SessionLocal() as session:
                for mid in created_memory_ids:
                    m = await session.get(AgentMemory, mid)
                    if m:
                        await session.delete(m)
                await session.commit()

                for cid in created_chunk_ids:
                    res = await session.execute(select(ContextEmbedding).where(ContextEmbedding.chunk_id == cid))
                    emb = res.scalar_one_or_none()
                    if emb:
                        await session.delete(emb)
                    chk = await session.get(ContextChunk, cid)
                    if chk:
                        await session.delete(chk)
                await session.commit()

                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    mem_res = await session.execute(select(AgentMemory).where(AgentMemory.organization_id == oid))
                    for m in mem_res.scalars().all():
                        await session.delete(m)
                    await session.commit()

                    chunk_res = await session.execute(select(ContextChunk).where(ContextChunk.organization_id == oid))
                    for chk in chunk_res.scalars().all():
                        emb_res = await session.execute(select(ContextEmbedding).where(ContextEmbedding.chunk_id == chk.id))
                        emb = emb_res.scalar_one_or_none()
                        if emb:
                            await session.delete(emb)
                        await session.delete(chk)
                    await session.commit()

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

    print("\nAll Memory & Context Cross-Tenant Isolation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_memory_context_tenant_isolation_flow())
