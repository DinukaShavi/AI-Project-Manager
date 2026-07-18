import math
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import BaseRepository
from app.models.context import ContextChunk, ContextEmbedding

class ContextRepository(BaseRepository[ContextChunk]):
    def __init__(self, session: AsyncSession):
        super().__init__(ContextChunk, session)

    async def create_chunk_with_embedding(
        self,
        organization_id: UUID,
        source_type: str,
        source_id: UUID,
        chunk_index: int,
        content: str,
        token_count: int,
        embedding_vector: List[float],
        project_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[ContextChunk, ContextEmbedding]:
        """Insert ContextChunk and its associated ContextEmbedding in database transaction."""
        chunk = ContextChunk(
            organization_id=organization_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            chunk_index=chunk_index,
            content=content,
            token_count=token_count,
            metadata_json=metadata or {}
        )
        self.session.add(chunk)
        await self.session.flush()

        embedding = ContextEmbedding(
            chunk_id=chunk.id,
            model_name="text-embedding-3-small",
            dimension=len(embedding_vector),
            embedding=embedding_vector
        )
        self.session.add(embedding)
        await self.session.commit()
        await self.session.refresh(chunk)
        await self.session.refresh(embedding)

        return chunk, embedding

    async def search_context(
        self,
        organization_id: UUID,
        query_embedding: List[float],
        project_id: Optional[UUID] = None,
        limit: int = 10
    ) -> List[Tuple[ContextChunk, float]]:
        """Perform semantic vector similarity search returning top-k matching ContextChunks."""
        query = select(ContextChunk, ContextEmbedding).join(
            ContextEmbedding, ContextChunk.id == ContextEmbedding.chunk_id
        ).where(ContextChunk.organization_id == organization_id)

        if project_id:
            query = query.where(ContextChunk.project_id == project_id)

        result = await self.session.execute(query)
        rows = result.all()

        if not rows:
            return []

        # Cosine Similarity Calculation: dot(u, v) / (||u|| * ||v||)
        def cosine_similarity(v1: List[float], v2: List[float]) -> float:
            if not v1 or not v2 or len(v1) != len(v2):
                return 0.0
            dot = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)

        scored_chunks = []
        for chunk, emb in rows:
            score = cosine_similarity(query_embedding, emb.embedding)
            scored_chunks.append((chunk, score))

        # Sort descending by similarity score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:limit]
