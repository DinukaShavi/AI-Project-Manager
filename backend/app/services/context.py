import json
from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.context.chunker import TextChunker
from app.context.embeddings import get_embedding_generator
from app.repositories.context import ContextRepository
from app.models.context import ContextChunk

MAX_RERANK_CANDIDATES = 20
RERANK_CANDIDATE_MULTIPLIER = 4


def _get_reranker_agent():
    """Minimal BaseAgent carrier for `_llm_call`'s real Claude/GPT-4o failover -- same pattern
    as `_PlannerLLM` (Phase 71, planner.py) and `_SentimentLLM` (Phase 72, slack_activity.py).
    `execute()` is never called. Defined lazily to avoid importing app.agents.base (which
    pulls in httpx/circuit-breaker/model-router machinery) for every ContextEngineService use,
    most of which never rerank."""
    from app.agents.base import BaseAgent

    class _RerankLLM(BaseAgent):
        async def execute(self, task_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            raise NotImplementedError("_RerankLLM is a carrier for _llm_call only.")

    return _RerankLLM(
        agent_name="ContextReranker", role="Semantic Search Relevance Reranker",
        system_prompt="You rerank search results by true relevance to a query.",
    )


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
        """Split text into semantic chunks, generate embeddings, and persist in vector store.

        Idempotent per (organization_id, source_type, source_id): re-indexing the same source
        (an edited PR/issue, or a redelivered event) replaces its prior chunks rather than
        accumulating duplicates.
        """
        await self.repository.delete_chunks_for_source(organization_id, source_type, source_id)

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
        top_k: int = 5,
        rerank: bool = False,
    ) -> List[Dict[str, Any]]:
        """Perform semantic search for query text across indexed organization context.

        `rerank` (Phase 78, opt-in, default off -- every existing caller's behavior is
        unchanged) over-fetches a larger real vector-similarity candidate pool and reranks it
        down to `top_k` via a real LLM relevance pass, falling back to the original
        vector-similarity order (already real, already correct) on any failure."""
        query_vector = await self.embedding_generator.generate_embedding(query_text)
        fetch_limit = min(top_k * RERANK_CANDIDATE_MULTIPLIER, MAX_RERANK_CANDIDATES) if rerank else top_k
        results = await self.repository.search_context(
            organization_id=organization_id,
            query_embedding=query_vector,
            project_id=project_id,
            limit=fetch_limit
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

        if rerank and len(formatted_results) > 1:
            # Worth reranking whenever there's more than one candidate to order, not only when
            # there's overflow beyond top_k -- reordering the exact top_k set by relevance is
            # real value on its own, not just trimming a larger pool.
            return await self._rerank(query_text, formatted_results, top_k)
        return formatted_results[:top_k]

    async def _rerank(self, query_text: str, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        numbered = "\n".join(f"[{i}] {c['content'][:300]}" for i, c in enumerate(candidates))
        system_prompt = (
            "You rerank semantic search results by true relevance to a query. Respond with "
            f"ONLY a JSON array of the indices of the top {top_k} most relevant results, "
            'ordered best-first, e.g. [3, 0, 7]. No prose, no markdown fences.'
        )
        user_prompt = f"Query: {query_text}\n\nCandidates:\n{numbered}"
        try:
            raw = await _get_reranker_agent()._llm_call(user_prompt, system_prompt, task_category="output_reflection")
            indices = json.loads(self._extract_json_array(raw))
            if not isinstance(indices, list):
                raise ValueError("Reranker response was not a JSON array.")
            reranked, seen = [], set()
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                    reranked.append(candidates[idx])
                    seen.add(idx)
                if len(reranked) >= top_k:
                    break
            if reranked:
                return reranked
        except Exception:
            pass
        return candidates[:top_k]

    @staticmethod
    def _extract_json_array(text: str) -> str:
        text = text.strip()
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON array found in reranker response.")
        return text[start:end + 1]
