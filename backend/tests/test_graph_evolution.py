import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.models.tenant import Organization, User
from app.db.session import SessionLocal
from app.services.graph_evolution import (
    get_graph_evolution_engine,
    KnowledgeGraphEvolutionEngine
)
from tests._auth_helpers import create_authenticated_headers

async def test_graph_evolution_flow():
    print("Initializing Knowledge Graph Relationship Weight Decay & Inference Pipeline validation tests...")
    engine = get_graph_evolution_engine()
    org_id = str(uuid.uuid4())

    # 1. Test Dynamic Weight Decay Formula Math Calculation
    print("\nTest 1: Testing Weight = BaseWeight * (1 - DecayFactor * AgeDays) formula...")
    # Base weight 1.0, age 30 days, decay_factor 0.01 -> 1.0 * (1 - 0.3) = 0.70
    decayed_30 = engine.calculate_decayed_weight(base_weight=1.0, age_days=30.0, decay_factor=0.01)
    assert decayed_30 == 0.70

    # Base weight 0.5, age 100 days, decay_factor 0.01 -> 0.5 * (1 - 1.0) = 0.0 -> floor 0.05
    decayed_floor = engine.calculate_decayed_weight(base_weight=0.5, age_days=100.0, decay_factor=0.01)
    assert decayed_floor == 0.05
    print("SUCCESS: Weight decay formula calculated accurately with minimum floor.")

    # 2. Test Entity Linker & Implicit Inference Pipeline (organization-scoped, Phase 83)
    print("\nTest 2: Testing Entity Linker & Event Inference Pipeline...")
    edge_blocked = engine.link_entities(org_id, "issue-101", "issue-102", "blocked_by")
    assert edge_blocked.base_weight == 1.0
    assert edge_blocked.organization_id == org_id

    events = [
        {"event_type": "commit_pushed", "source_id": "commit-abc", "target_id": "pr-404"},
        {"event_type": "incident_reported", "source_id": "service-billing", "target_id": "issue-999"}
    ]
    inferred = engine.infer_implicit_edges(org_id, events)
    assert len(inferred) == 2
    assert inferred[0].relation_type == "merged_in"
    assert inferred[1].relation_type == "blocked_by"
    print("SUCCESS: Entity linker and event inference pipeline verified.")

    # 3. Test Graph Decay Sweep & Graph Traverser (organization-scoped, Phase 83)
    print("\nTest 3: Testing Decay Sweep and Graph Traverser filtering...")
    sweep_summary = engine.apply_decay_sweep(org_id, simulated_age_days=30.0, decay_factor=0.01)
    assert sweep_summary["total_edges_evaluated"] >= 3
    assert sweep_summary["updated_count"] >= 3

    trav_res = engine.traverse_graph(org_id, "issue-101", min_weight=0.50)
    assert trav_res["start_node_id"] == "issue-101"
    assert len(trav_res["active_outbound_edges"]) >= 1
    print("SUCCESS: Decay sweep and graph traverser verified.")

    # 4. Test REST API Endpoints require real authentication and real tenant isolation:
    #    Org A's traverse_graph must not return Org B's edges even when source_id/target_id
    #    collide between the two orgs, and apply_decay_sweep only mutates the calling org's
    #    own edges (Phase 83).
    print("\nTest 4: Testing Graph Evolution HTTP REST API endpoints...")
    real_org_a_id = None
    real_org_b_id = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Graph Evo Org A {uuid.uuid4().hex[:6]}", domain=f"gevo-a-{uuid.uuid4().hex[:6]}.com")
                org_b = Organization(name=f"Graph Evo Org B {uuid.uuid4().hex[:6]}", domain=f"gevo-b-{uuid.uuid4().hex[:6]}.com")
                session.add_all([org_a, org_b])
                await session.commit()
                real_org_a_id = org_a.id
                real_org_b_id = org_b.id

            # Unauthenticated requests must be rejected.
            for method, path, body in (
                ("post", "/api/v1/graph-evolution/link", {"source_id": "dev-user-1", "target_id": "task-500", "relation_type": "assigned_to"}),
                ("post", "/api/v1/graph-evolution/infer", {"events": [{"event_type": "pr_merged", "source_id": "pr-10", "target_id": "main-branch"}]}),
                ("post", "/api/v1/graph-evolution/decay-sweep", {"simulated_age_days": 15.0, "decay_factor": 0.01}),
                ("get", "/api/v1/graph-evolution/traverse/dev-user-1", None),
            ):
                res = await (client.get(path) if method == "get" else client.post(path, json=body))
                assert res.status_code in (401, 403), f"Expected 401/403 for unauthenticated {method} {path}, got {res.status_code}: {res.text}"
            print("SUCCESS: All four endpoints correctly reject unauthenticated requests.")

            headers_a = await create_authenticated_headers(client, real_org_a_id)
            headers_b = await create_authenticated_headers(client, real_org_b_id)

            # Both orgs link an edge using the SAME source_id/target_id/relation_type -- a
            # colliding node-id namespace is realistic (e.g. shared Jira key formats).
            res_link_a = await client.post(
                "/api/v1/graph-evolution/link",
                json={"source_id": "shared-node-1", "target_id": "shared-node-2", "relation_type": "assigned_to"},
                headers=headers_a,
            )
            assert res_link_a.status_code == 200, res_link_a.text
            assert res_link_a.json()["base_weight"] == 0.7

            res_link_b = await client.post(
                "/api/v1/graph-evolution/link",
                json={"source_id": "shared-node-1", "target_id": "shared-node-2", "relation_type": "assigned_to", "base_weight": 0.42},
                headers=headers_b,
            )
            assert res_link_b.status_code == 200, res_link_b.text
            assert res_link_b.json()["base_weight"] == 0.42

            # POST /api/v1/graph-evolution/infer
            res_inf = await client.post(
                "/api/v1/graph-evolution/infer",
                json={"events": [{"event_type": "pr_merged", "source_id": "pr-10", "target_id": "main-branch"}]},
                headers=headers_a,
            )
            assert res_inf.status_code == 200, res_inf.text
            assert res_inf.json()["total_inferred"] == 1

            # GET traverse for Org A must see ONLY Org A's edge weight (0.7), never Org B's (0.42).
            res_trv_a = await client.get("/api/v1/graph-evolution/traverse/shared-node-1?min_weight=0.10", headers=headers_a)
            assert res_trv_a.status_code == 200, res_trv_a.text
            edges_a = res_trv_a.json()["active_outbound_edges"]
            assert any(e["target_id"] == "shared-node-2" and e["base_weight"] == 0.7 for e in edges_a), edges_a
            assert not any(e["base_weight"] == 0.42 for e in edges_a), "Org A traverse leaked Org B's edge weight!"

            # GET traverse for Org B must see ONLY Org B's edge weight (0.42), never Org A's (0.7).
            res_trv_b = await client.get("/api/v1/graph-evolution/traverse/shared-node-1?min_weight=0.10", headers=headers_b)
            assert res_trv_b.status_code == 200, res_trv_b.text
            edges_b = res_trv_b.json()["active_outbound_edges"]
            assert any(e["target_id"] == "shared-node-2" and e["base_weight"] == 0.42 for e in edges_b), edges_b
            assert not any(e["base_weight"] == 0.7 for e in edges_b), "Org B traverse leaked Org A's edge weight!"
            print("SUCCESS: traverse_graph does not leak edges across organizations even when node ids collide.")

            # POST /api/v1/graph-evolution/decay-sweep for Org A must only report/mutate Org A's
            # own edges, never touching or counting Org B's.
            res_swp_a = await client.post(
                "/api/v1/graph-evolution/decay-sweep",
                json={"simulated_age_days": 15.0, "decay_factor": 0.01},
                headers=headers_a,
            )
            assert res_swp_a.status_code == 200, res_swp_a.text

            # After the sweep, Org B's edge weight must be unchanged (still 0.42) -- proving the
            # sweep triggered by Org A never mutated Org B's edges.
            res_trv_b_after = await client.get("/api/v1/graph-evolution/traverse/shared-node-1?min_weight=0.10", headers=headers_b)
            edges_b_after = res_trv_b_after.json()["active_outbound_edges"]
            assert any(e["current_weight"] == 0.42 for e in edges_b_after), edges_b_after
            print("SUCCESS: decay-sweep triggered by one organization does not mutate another organization's edges.")

            print("SUCCESS: Knowledge Graph Evolution REST API endpoints verified -- real auth required, fully tenant-isolated.")
        finally:
            for org_id_cleanup in (real_org_a_id, real_org_b_id):
                if not org_id_cleanup:
                    continue
                async with SessionLocal() as session:
                    user_res = await session.execute(select(User).where(User.organization_id == org_id_cleanup))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    org_row = await session.get(Organization, org_id_cleanup)
                    if org_row:
                        await session.delete(org_row)
                    await session.commit()

    print("\nAll Knowledge Graph Evolution System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_graph_evolution_flow())
