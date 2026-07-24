from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from collections import deque
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.graph import KnowledgeGraphEdge

@dataclass
class EntityNode:
    urn: str
    type: str  # e.g., 'jira_issue', 'pull_request', 'developer', 'sprint', 'slack_message', 'meeting'
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Edge:
    source_urn: str
    target_urn: str
    relation_type: str  # e.g., 'ASSIGNED_TO', 'BLOCKS', 'RESOLVES', 'DISCUSSED_IN', 'SCHEDULED_IN', 'BELONGS_TO'
    weight: float = 1.0

class ProjectKnowledgeGraph:
    def __init__(self):
        self.nodes: Dict[str, EntityNode] = {}
        self.edges: List[Edge] = []
        self.adj: Dict[str, List[Edge]] = {}
        self.rev_adj: Dict[str, List[Edge]] = {}

    def add_entity(self, node: EntityNode) -> None:
        """Add or update an entity node in the graph."""
        self.nodes[node.urn] = node
        if node.urn not in self.adj:
            self.adj[node.urn] = []
        if node.urn not in self.rev_adj:
            self.rev_adj[node.urn] = []

    def add_edge(self, source_urn: str, target_urn: str, relation_type: str, weight: float = 1.0) -> Edge:
        """Add a directed relationship edge between two entities."""
        if source_urn not in self.nodes:
            self.add_entity(EntityNode(urn=source_urn, type="generic"))
        if target_urn not in self.nodes:
            self.add_entity(EntityNode(urn=target_urn, type="generic"))

        edge = Edge(source_urn=source_urn, target_urn=target_urn, relation_type=relation_type, weight=weight)
        self.edges.append(edge)
        self.adj[source_urn].append(edge)
        self.rev_adj[target_urn].append(edge)
        return edge

    def get_subgraph_context(self, entity_urn: str, max_depth: int = 2) -> Dict[str, Any]:
        """Extract a localized subgraph of nodes and edges within max_depth steps for prompt injection."""
        if entity_urn not in self.nodes:
            return {"nodes": [], "edges": []}

        visited_nodes: Set[str] = {entity_urn}
        queue = deque([(entity_urn, 0)])
        result_edges: List[Dict[str, Any]] = []

        while queue:
            curr_urn, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Traversal along outgoing edges
            for edge in self.adj.get(curr_urn, []):
                result_edges.append({
                    "source": edge.source_urn,
                    "target": edge.target_urn,
                    "relation": edge.relation_type,
                    "weight": edge.weight
                })
                if edge.target_urn not in visited_nodes:
                    visited_nodes.add(edge.target_urn)
                    queue.append((edge.target_urn, depth + 1))

            # Traversal along incoming edges
            for edge in self.rev_adj.get(curr_urn, []):
                result_edges.append({
                    "source": edge.source_urn,
                    "target": edge.target_urn,
                    "relation": edge.relation_type,
                    "weight": edge.weight
                })
                if edge.source_urn not in visited_nodes:
                    visited_nodes.add(edge.source_urn)
                    queue.append((edge.source_urn, depth + 1))

        # Deduplicate edges
        unique_edges = []
        seen_edges = set()
        for e in result_edges:
            key = (e["source"], e["target"], e["relation"])
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(e)

        result_nodes = [
            {"urn": urn, "type": self.nodes[urn].type, "properties": self.nodes[urn].properties}
            for urn in visited_nodes if urn in self.nodes
        ]

        return {"nodes": result_nodes, "edges": unique_edges}

    def find_bottleneck_clusters(self) -> List[Dict[str, Any]]:
        """Detect dependency bottlenecks, high-degree blocked issues, and cycle clusters."""
        bottlenecks = []
        for urn, node in self.nodes.items():
            incoming_blocks = [e for e in self.rev_adj.get(urn, []) if e.relation_type == "BLOCKS"]
            outgoing_blocks = [e for e in self.adj.get(urn, []) if e.relation_type == "BLOCKS"]
            
            # High incoming blocker density
            if len(incoming_blocks) >= 2 or len(outgoing_blocks) >= 2:
                bottlenecks.append({
                    "urn": urn,
                    "type": node.type,
                    "blocking_count": len(outgoing_blocks),
                    "blocked_by_count": len(incoming_blocks),
                    "properties": node.properties
                })
        return bottlenecks

    def traverse_root_cause(self, target_urn: str) -> List[Dict[str, Any]]:
        """Trace root causes backward through 'BLOCKS', 'DEPENDS_ON', or 'ASSIGNED_TO' links."""
        path = []
        if target_urn not in self.nodes:
            return path

        visited = set()
        queue = deque([target_urn])

        while queue:
            curr = queue.popleft()
            if curr in visited:
                continue
            visited.add(curr)

            if curr in self.nodes:
                path.append({
                    "urn": curr,
                    "type": self.nodes[curr].type,
                    "properties": self.nodes[curr].properties
                })

            for edge in self.rev_adj.get(curr, []):
                if edge.relation_type in ("BLOCKS", "DEPENDS_ON", "ASSIGNED_TO"):
                    if edge.source_urn not in visited:
                        queue.append(edge.source_urn)

        return path

    async def load_from_db(self, db: AsyncSession, organization_id: Any, project_id: Any) -> None:
        """Load graph structure from knowledge_graph_edges table."""
        stmt = select(KnowledgeGraphEdge).where(
            KnowledgeGraphEdge.organization_id == organization_id,
            KnowledgeGraphEdge.project_id == project_id
        )
        result = await db.execute(stmt)
        edges = result.scalars().all()

        for db_edge in edges:
            self.add_edge(
                source_urn=db_edge.source_urn,
                target_urn=db_edge.target_urn,
                relation_type=db_edge.relation_type,
                weight=float(db_edge.weight) if db_edge.weight else 1.0
            )

    async def save_to_db(self, db: AsyncSession, organization_id: Any, project_id: Any) -> None:
        """Persist graph edges to database."""
        for edge in self.edges:
            db_edge = KnowledgeGraphEdge(
                organization_id=organization_id,
                project_id=project_id,
                source_urn=edge.source_urn,
                target_urn=edge.target_urn,
                relation_type=edge.relation_type,
                weight=edge.weight
            )
            db.add(db_edge)
        await db.flush()
