from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.context.chunker import TextChunker
from app.context.embeddings import get_embedding_generator
from app.repositories.context import ContextRepository
from app.models.context import ContextChunk

class ContextEngineService:
    def __init__(self, session: AsyncSession):
        """Context Engine Service managing document indexing and semantic retrieval."""
        self.session = session
        self.chunker = TextChunker()
        self.embedding_generator = get_embedding_generator()
        self.repository = ContextRepository(session)

    async def index_document(
        self,
        organization_id: UUID,
        source_type: str,
        source_id: UUID,
        text: str,
        project_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[ContextChunk]:
        """Split text into semantic chunks, generate embeddings, and persist in vector store."""
        chunks = self.chunker.chunk_text(text)
        indexed_chunks = []

        for chunk_item in chunks:
            chunk_content = chunk_item["content"]
            chunk_idx = chunk_item["chunk_index"]
            token_count = chunk_item["token_count"]

            # Generate 1536-dimensional vector embedding
            embedding_vector = await self.embedding_generator.generate_embedding(chunk_content)

            # Persist in PostgreSQL ContextChunk and ContextEmbedding tables
            db_chunk, _ = await self.repository.create_chunk_with_embedding(
                organization_id=organization_id,
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                chunk_index=chunk_idx,
                content=chunk_content,
                token_count=token_count,
                embedding_vector=embedding_vector,
                metadata=metadata
            )
            indexed_chunks.append(db_chunk)

        return indexed_chunks

    async def search_context(
        self,
        organization_id: UUID,
        query_text: str,
        project_id: Optional[UUID] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Perform semantic search for query text across indexed organization context."""
        query_vector = await self.embedding_generator.generate_embedding(query_text)
        results = await self.repository.search_context(
            organization_id=organization_id,
            query_embedding=query_vector,
            project_id=project_id,
            limit=top_k
        )

        formatted_results = []
        for chunk, score in results:
            formatted_results.append({
                "chunk_id": str(chunk.id),
                "source_type": chunk.source_type,
                "source_id": str(chunk.source_id),
                "content": chunk.content,
                "score": float(score),
                "token_count": chunk.token_count,
                "metadata": chunk.metadata_json
            })

        return formatted_results
