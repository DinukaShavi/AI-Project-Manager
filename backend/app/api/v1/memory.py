from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.memory import MemoryService

router = APIRouter()

class MemoryStoreRequest(BaseModel):
    organization_id: UUID
    memory_type: str = Field(..., description="Memory type: 'short_term', 'long_term', 'entity'")
    key: Optional[str] = None
    content: Optional[str] = None
    value_json: Optional[Dict[str, Any]] = None
    agent_type: Optional[str] = None
    project_id: Optional[UUID] = None

class MemorySearchRequest(BaseModel):
    organization_id: UUID
    query: str = Field(..., description="Query text to search long-term memories")
    project_id: Optional[UUID] = None
    limit: int = Field(5, ge=1, le=50)

@router.post("", status_code=status.HTTP_201_CREATED)
async def store_memory(
    payload: MemoryStoreRequest,
    db: AsyncSession = Depends(get_db)
):
    """Store short-term, long-term, or entity memory entry."""
    service = MemoryService(db)
    memory = await service.store_memory(
        organization_id=payload.organization_id,
        memory_type=payload.memory_type,
        key=payload.key,
        content=payload.content,
        value_json=payload.value_json,
        agent_type=payload.agent_type,
        project_id=payload.project_id
    )
    return {
        "status": "stored",
        "memory_id": str(memory.id),
        "memory_type": memory.memory_type,
        "key": memory.key
    }

@router.get("", status_code=status.HTTP_200_OK)
async def recall_memory(
    organization_id: UUID,
    key: str,
    memory_type: Optional[str] = None,
    agent_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Recall memory entry by key."""
    service = MemoryService(db)
    memory = await service.recall_memory(
        organization_id=organization_id,
        key=key,
        memory_type=memory_type,
        agent_type=agent_type
    )
    if not memory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory key '{key}' not found.")
    return {
        "memory_id": str(memory.id),
        "key": memory.key,
        "memory_type": memory.memory_type,
        "agent_type": memory.agent_type,
        "content": memory.content,
        "value_json": memory.value_json
    }

@router.post("/search", status_code=status.HTTP_200_OK)
async def search_memory(
    payload: MemorySearchRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute vector similarity search over long-term agent memories."""
    service = MemoryService(db)
    results = await service.search_long_term_memory(
        organization_id=payload.organization_id,
        query_text=payload.query,
        project_id=payload.project_id,
        limit=payload.limit
    )
    return {
        "query": payload.query,
        "results_count": len(results),
        "results": results
    }
