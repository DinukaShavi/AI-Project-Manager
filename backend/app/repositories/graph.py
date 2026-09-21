from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.graph import KnowledgeGraphEdge


class GraphRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_edge(
        self,
        organization_id: UUID,
        project_id: UUID,
        source_urn: str,
        target_urn: str,
        relation_type: str,
        weight: float = 1.0,
    ) -> KnowledgeGraphEdge:
        """Return the existing edge unchanged if the exact same (org, project, source,
        target, relation) triple already exists, otherwise insert it -- redelivered events
        (at-least-once Event Bus delivery, or a re-synced issue) must not accumulate
        duplicate edges."""
        res = await self.session.execute(
            select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.organization_id == organization_id,
                KnowledgeGraphEdge.project_id == project_id,
                KnowledgeGraphEdge.source_urn == source_urn,
                KnowledgeGraphEdge.target_urn == target_urn,
                KnowledgeGraphEdge.relation_type == relation_type,
            )
        )
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        edge = KnowledgeGraphEdge(
            organization_id=organization_id,
            project_id=project_id,
            source_urn=source_urn,
            target_urn=target_urn,
            relation_type=relation_type,
            weight=weight,
        )
        self.session.add(edge)
        await self.session.flush()
        return edge
