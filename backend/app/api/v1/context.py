from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.context import ContextEngineService

router = APIRouter()

class IndexRequest(BaseModel):
    organization_id: UUID
    source_type: str = Field(..., description="Source entity type (e.g. pr, issue, doc, chat)")
    source_id: UUID
    text: str = Field(..., description="Raw text content to chunk and index")
    project_id: Optional[UUID] = None
    metadata: Optional[Dict[str, Any]] = None

class SearchRequest(BaseModel):
    organization_id: UUID
    query: str = Field(..., description="Semantic search query")
    project_id: Optional[UUID] = None
    top_k: int = Field(5, ge=1, le=50)

@router.post("/index", status_code=status.HTTP_201_CREATED)
async def index_document(
    payload: IndexRequest,
    db: AsyncSession = Depends(get_db)
):
    """Chunk, embed, and index a technical document into the Context Engine."""
    service = ContextEngineService(db)
    chunks = await service.index_document(
        organization_id=payload.organization_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        text=payload.text,
        project_id=payload.project_id,
        metadata=payload.metadata
    )
    return {
        "status": "indexed",
        "chunks_indexed": len(chunks),
        "chunk_ids": [str(c.id) for c in chunks]
    }

@router.post("/search")
async def search_context(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute vector semantic search across indexed technical context."""
    service = ContextEngineService(db)
    results = await service.search_context(
        organization_id=payload.organization_id,
        query_text=payload.query,
        project_id=payload.project_id,
        top_k=payload.top_k
    )
    return {
        "query": payload.query,
        "results_count": len(results),
        "results": results
    }
