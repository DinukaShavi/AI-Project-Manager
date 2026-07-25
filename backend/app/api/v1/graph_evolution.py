from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from app.services.graph_evolution import get_graph_evolution_engine

router = APIRouter(prefix="/graph-evolution", tags=["Knowledge Graph Evolution"])

class LinkEntitiesRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str # blocked_by, depends_on, merged_in, assigned_to, reviews, mentioned_in
    base_weight: Optional[float] = None

class InferEventsRequest(BaseModel):
    events: List[Dict[str, Any]]

class DecaySweepRequest(BaseModel):
    simulated_age_days: float = 30.0
    decay_factor: float = 0.01

@router.post("/link")
async def link_entities(payload: LinkEntitiesRequest):
    """Explicitly link two development entities in the Knowledge Graph with a relationship weight."""
    engine = get_graph_evolution_engine()
    edge = engine.link_entities(
        source_id=payload.source_id,
        target_id=payload.target_id,
        relation_type=payload.relation_type,
        base_weight=payload.base_weight
    )
    return {
        "message": "Edge created successfully.",
        "edge_id": edge.id,
        "relation_type": edge.relation_type,
        "base_weight": edge.base_weight,
        "current_weight": edge.current_weight
    }

@router.post("/infer")
async def infer_implicit_edges(payload: InferEventsRequest):
    """Run inference pipeline over event payloads to extract implicit dependency edges."""
    engine = get_graph_evolution_engine()
    inferred_edges = engine.infer_implicit_edges(payload.events)
    return {
        "total_inferred": len(inferred_edges),
        "edges": [
            {
                "edge_id": e.id,
                "source_id": e.source_id,
                "target_id": e.target_id,
                "relation_type": e.relation_type,
                "current_weight": e.current_weight
            }
            for e in inferred_edges
        ]
    }

@router.post("/decay-sweep")
async def apply_decay_sweep(payload: DecaySweepRequest):
    """Trigger relationship weight decay sweep using Weight = BaseWeight * (1 - DecayFactor * AgeDays)."""
    engine = get_graph_evolution_engine()
    summary = engine.apply_decay_sweep(
        simulated_age_days=payload.simulated_age_days,
        decay_factor=payload.decay_factor
    )
    return summary

@router.get("/traverse/{start_node_id}")
async def traverse_graph(start_node_id: str, min_weight: float = 0.10):
    """Traverse knowledge graph from a starting node, filtering out decayed edges below min_weight."""
    engine = get_graph_evolution_engine()
    return engine.traverse_graph(start_node_id, min_weight=min_weight)
