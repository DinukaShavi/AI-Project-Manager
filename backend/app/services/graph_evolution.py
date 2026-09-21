import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

BASE_RELATION_WEIGHTS: Dict[str, float] = {
    "blocked_by": 1.0,
    "depends_on": 0.9,
    "merged_in": 0.8,
    "assigned_to": 0.7,
    "reviews": 0.6,
    "mentioned_in": 0.5,
}

@dataclass
class GraphEdgeRecord:
    id: str
    organization_id: str
    source_id: str
    target_id: str
    relation_type: str
    base_weight: float
    current_weight: float
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

class KnowledgeGraphEvolutionEngine:
    """Enterprise Knowledge Graph Evolution Engine with Decay Sweep & Inference Pipeline.

    Edges are keyed by (organization_id, source_id->relation->target_id) -- real tenant
    scoping (Phase 83), since source_id/target_id are caller-chosen strings that can
    plausibly collide across organizations (e.g. a Jira key format like "PROJ-123" is common
    to many real orgs) and this engine has no other tenant boundary."""

    def __init__(self):
        self.edges: Dict[str, GraphEdgeRecord] = {}

    @staticmethod
    def _edge_key(organization_id: str, source_id: str, relation_type: str, target_id: str) -> str:
        return f"{organization_id}:{source_id}->{relation_type}->{target_id}"

    def link_entities(
        self,
        organization_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
        base_weight: Optional[float] = None
    ) -> GraphEdgeRecord:
        """Create or update a weighted relationship edge between two entities, scoped to the
        real calling organization."""
        edge_key = self._edge_key(organization_id, source_id, relation_type, target_id)
        bw = base_weight if base_weight is not None else BASE_RELATION_WEIGHTS.get(relation_type, 0.5)

        now = time.time()
        edge = GraphEdgeRecord(
            id=edge_key,
            organization_id=organization_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            base_weight=bw,
            current_weight=bw,
            created_at=now,
            last_updated=now
        )
        self.edges[edge_key] = edge
        return edge

    def infer_implicit_edges(self, organization_id: str, events: List[Dict[str, Any]]) -> List[GraphEdgeRecord]:
        """
        Inference Pipeline:
        Scans event payloads (commits, PR descriptions, incident reports) to infer implicit edges.
        Example: PR mentions issue PROJ-123 -> infer 'merged_in' or 'mentioned_in'.
        """
        inferred = []
        for ev in events:
            ev_type = ev.get("event_type", "")
            source_id = ev.get("source_id", "source-0")
            target_id = ev.get("target_id", "target-0")

            if "commit" in ev_type or "pr" in ev_type:
                edge = self.link_entities(organization_id, source_id, target_id, "merged_in")
                inferred.append(edge)
            elif "incident" in ev_type:
                edge = self.link_entities(organization_id, source_id, target_id, "blocked_by")
                inferred.append(edge)
            else:
                edge = self.link_entities(organization_id, source_id, target_id, "mentioned_in")
                inferred.append(edge)

        return inferred

    def calculate_decayed_weight(
        self,
        base_weight: float,
        age_days: float,
        decay_factor: float = 0.01
    ) -> float:
        """
        Dynamic Weight Decay Formula:
        Weight = BaseWeight * (1.0 - DecayFactor * AgeDays)
        Floor at 0.05 minimum weight threshold.
        """
        decayed = base_weight * (1.0 - (decay_factor * age_days))
        return max(0.05, round(decayed, 4))

    def apply_decay_sweep(self, organization_id: str, simulated_age_days: float = 0.0, decay_factor: float = 0.01) -> Dict[str, Any]:
        """
        Decay Sweep Pipeline:
        Recalculates current_weight for the calling organization's own active graph edges
        based on age in days -- never touches another org's edges (Phase 83).
        """
        now = time.time()
        updated_count = 0
        org_edges = [e for e in self.edges.values() if e.organization_id == organization_id]

        for edge in org_edges:
            if simulated_age_days > 0.0:
                age = simulated_age_days
            else:
                age = (now - edge.created_at) / 86400.0 # convert seconds to days

            edge.current_weight = self.calculate_decayed_weight(edge.base_weight, age, decay_factor)
            edge.last_updated = now
            updated_count += 1

        return {
            "total_edges_evaluated": len(org_edges),
            "updated_count": updated_count,
            "simulated_age_days": simulated_age_days,
            "decay_factor": decay_factor
        }

    def traverse_graph(self, organization_id: str, start_node_id: str, min_weight: float = 0.10) -> Dict[str, Any]:
        """Traverse the calling organization's own knowledge graph from a starting node,
        filtering out decayed edges below min_weight -- never returns another org's edges
        even if source_id/target_id values happen to collide (Phase 83)."""
        outbound = [
            {
                "edge_id": e.id,
                "target_id": e.target_id,
                "relation_type": e.relation_type,
                "current_weight": e.current_weight,
                "base_weight": e.base_weight
            }
            for e in self.edges.values()
            if e.organization_id == organization_id and e.source_id == start_node_id and e.current_weight >= min_weight
        ]
        return {
            "start_node_id": start_node_id,
            "active_outbound_edges": outbound,
            "total_active_edges": len(outbound)
        }


# Singleton Instance Manager
_graph_evolution_engine_instance: Optional[KnowledgeGraphEvolutionEngine] = None

def get_graph_evolution_engine() -> KnowledgeGraphEvolutionEngine:
    """Get global KnowledgeGraphEvolutionEngine singleton instance."""
    global _graph_evolution_engine_instance
    if _graph_evolution_engine_instance is None:
        _graph_evolution_engine_instance = KnowledgeGraphEvolutionEngine()
    return _graph_evolution_engine_instance
