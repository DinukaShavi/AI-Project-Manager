import math
from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.context.embeddings import get_embedding_generator
from app.models.memory import AgentMemory

class MemoryService:
    def __init__(self, session: AsyncSession):
        """Memory Service managing persistent multi-tiered memory records in PostgreSQL."""
        self.session = session
        self.embedding_generator = get_embedding_generator()

    async def store_memory(
        self,
        organization_id: UUID,
        memory_type: str, # 'short_term', 'long_term', 'entity'
        key: Optional[str] = None,
        content: Optional[str] = None,
        value_json: Optional[Dict[str, Any]] = None,
        agent_type: Optional[str] = None,
        project_id: Optional[UUID] = None
    ) -> AgentMemory:
        """Store short-term, entity, or long-term vector memory in database."""
        embedding_vec = None
        if memory_type == "long_term" and content:
            embedding_vec = await self.embedding_generator.generate_embedding(content)

        memory = AgentMemory(
            organization_id=organization_id,
            project_id=project_id,
            agent_type=agent_type,
            memory_type=memory_type,
            key=key,
            content=content,
            value_json=value_json or {},
            embedding=embedding_vec
        )
        self.session.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def recall_memory(
        self,
        organization_id: UUID,
        key: str,
        memory_type: Optional[str] = None,
        agent_type: Optional[str] = None
    ) -> Optional[AgentMemory]:
        """Fetch memory entry by key."""
        query = select(AgentMemory).where(
            AgentMemory.organization_id == organization_id,
            AgentMemory.key == key
        )
        if memory_type:
            query = query.where(AgentMemory.memory_type == memory_type)
        if agent_type:
            query = query.where(AgentMemory.agent_type == agent_type)

        res = await self.session.execute(query)
        return res.scalar_one_or_none()

    async def search_long_term_memory(
        self,
        organization_id: UUID,
        query_text: str,
        project_id: Optional[UUID] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Perform vector similarity search across long-term agent memories.

        Uses pgvector's native <=> cosine-distance operator (ORDER BY + LIMIT pushed down to
        Postgres) when settings.USE_PGVECTOR is enabled — matching the same real-column-type
        gate used by ContextRepository.search_context. Falls back to the full-scan Python
        cosine similarity otherwise (the actual local dev default, since pgvector isn't
        installed there), preserving prior behavior exactly.
        """
        from app.core.config import settings
        query_vec = await self.embedding_generator.generate_embedding(query_text)

        if settings.USE_PGVECTOR:
            top_matches = await self._search_long_term_memory_native(organization_id, query_vec, project_id, limit)
        else:
            top_matches = await self._search_long_term_memory_python(organization_id, query_vec, project_id, limit)

        return [
            {
                "memory_id": str(mem.id),
                "key": mem.key,
                "content": mem.content,
                "score": float(score),
                "agent_type": mem.agent_type,
                "value_json": mem.value_json
            }
            for mem, score in top_matches
        ]

    async def _search_long_term_memory_native(
        self,
        organization_id: UUID,
        query_vec: List[float],
        project_id: Optional[UUID],
        limit: int
    ):
        distance_expr = AgentMemory.embedding.cosine_distance(query_vec)
        query = select(AgentMemory, distance_expr.label("distance")).where(
            AgentMemory.organization_id == organization_id,
            AgentMemory.memory_type == "long_term",
            AgentMemory.embedding != None
        )
        if project_id:
            query = query.where(AgentMemory.project_id == project_id)
        query = query.order_by(distance_expr).limit(limit)

        res = await self.session.execute(query)
        # cosine_distance = 1 - cosine_similarity; convert back to preserve the existing
        # "higher score = more relevant" contract.
        return [(mem, 1.0 - float(distance)) for mem, distance in res.all()]

    async def _search_long_term_memory_python(
        self,
        organization_id: UUID,
        query_vec: List[float],
        project_id: Optional[UUID],
        limit: int
    ):
        query = select(AgentMemory).where(
            AgentMemory.organization_id == organization_id,
            AgentMemory.memory_type == "long_term",
            AgentMemory.embedding != None
        )
        if project_id:
            query = query.where(AgentMemory.project_id == project_id)

        res = await self.session.execute(query)
        memories = res.scalars().all()

        def cosine_similarity(v1: List[float], v2: List[float]) -> float:
            if not v1 or not v2 or len(v1) != len(v2):
                return 0.0
            dot = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)

        scored_memories = [(mem, cosine_similarity(query_vec, mem.embedding)) for mem in memories]
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        return scored_memories[:limit]
