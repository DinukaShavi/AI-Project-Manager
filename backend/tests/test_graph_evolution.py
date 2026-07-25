import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.graph_evolution import (
    get_graph_evolution_engine,
    KnowledgeGraphEvolutionEngine
)

async def test_graph_evolution_flow():
    print("Initializing Knowledge Graph Relationship Weight Decay & Inference Pipeline validation tests...")
    engine = get_graph_evolution_engine()

    # 1. Test Dynamic Weight Decay Formula Math Calculation
    print("\nTest 1: Testing Weight = BaseWeight * (1 - DecayFactor * AgeDays) formula...")
    # Base weight 1.0, age 30 days, decay_factor 0.01 -> 1.0 * (1 - 0.3) = 0.70
    decayed_30 = engine.calculate_decayed_weight(base_weight=1.0, age_days=30.0, decay_factor=0.01)
    assert decayed_30 == 0.70

    # Base weight 0.5, age 100 days, decay_factor 0.01 -> 0.5 * (1 - 1.0) = 0.0 -> floor 0.05
    decayed_floor = engine.calculate_decayed_weight(base_weight=0.5, age_days=100.0, decay_factor=0.01)
    assert decayed_floor == 0.05
    print("SUCCESS: Weight decay formula calculated accurately with minimum floor.")

    # 2. Test Entity Linker & Implicit Inference Pipeline
    print("\nTest 2: Testing Entity Linker & Event Inference Pipeline...")
    edge_blocked = engine.link_entities("issue-101", "issue-102", "blocked_by")
    assert edge_blocked.base_weight == 1.0

    events = [
        {"event_type": "commit_pushed", "source_id": "commit-abc", "target_id": "pr-404"},
        {"event_type": "incident_reported", "source_id": "service-billing", "target_id": "issue-999"}
    ]
    inferred = engine.infer_implicit_edges(events)
    assert len(inferred) == 2
    assert inferred[0].relation_type == "merged_in"
    assert inferred[1].relation_type == "blocked_by"
    print("SUCCESS: Entity linker and event inference pipeline verified.")

    # 3. Test Graph Decay Sweep & Graph Traverser
    print("\nTest 3: Testing Decay Sweep and Graph Traverser filtering...")
    sweep_summary = engine.apply_decay_sweep(simulated_age_days=30.0, decay_factor=0.01)
    assert sweep_summary["total_edges_evaluated"] >= 3
    assert sweep_summary["updated_count"] >= 3

    trav_res = engine.traverse_graph("issue-101", min_weight=0.50)
    assert trav_res["start_node_id"] == "issue-101"
    assert len(trav_res["active_outbound_edges"]) >= 1
    print("SUCCESS: Decay sweep and graph traverser verified.")

    # 4. Test REST API Endpoints
    print("\nTest 4: Testing Graph Evolution HTTP REST API endpoints...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST /api/v1/graph-evolution/link
        res_link = await client.post(
            "/api/v1/graph-evolution/link",
            json={"source_id": "dev-user-1", "target_id": "task-500", "relation_type": "assigned_to"}
        )
        assert res_link.status_code == 200
        assert res_link.json()["base_weight"] == 0.7

        # POST /api/v1/graph-evolution/infer
        res_inf = await client.post(
            "/api/v1/graph-evolution/infer",
            json={"events": [{"event_type": "pr_merged", "source_id": "pr-10", "target_id": "main-branch"}]}
        )
        assert res_inf.status_code == 200
        assert res_inf.json()["total_inferred"] == 1

        # POST /api/v1/graph-evolution/decay-sweep
        res_swp = await client.post(
            "/api/v1/graph-evolution/decay-sweep",
            json={"simulated_age_days": 15.0, "decay_factor": 0.01}
        )
        assert res_swp.status_code == 200

        # GET /api/v1/graph-evolution/traverse/dev-user-1
        res_trv = await client.get("/api/v1/graph-evolution/traverse/dev-user-1?min_weight=0.10")
        assert res_trv.status_code == 200
        assert res_trv.json()["total_active_edges"] >= 1

        print("SUCCESS: Knowledge Graph Evolution REST API endpoints verified.")

    print("\nAll Knowledge Graph Evolution System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_graph_evolution_flow())
