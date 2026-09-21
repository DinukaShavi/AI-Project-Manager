from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from app.api.deps import get_current_user
from app.models.tenant import User
from app.services.memory_lifecycle import get_memory_lifecycle_engine

router = APIRouter(prefix="/memory-lifecycle", tags=["Memory Lifecycle & Vector GC"])

class CompressRequest(BaseModel):
    conversation_id: str
    messages: List[Dict[str, Any]]
    message_threshold: int = 10

class GarbageCollectRequest(BaseModel):
    memory_records: List[Dict[str, Any]]
    retention_days: int = 90

@router.post("/compress")
async def compress_conversation(
    payload: CompressRequest,
    current_user: User = Depends(get_current_user),
):
    """Summarize older messages exceeding threshold and index into pgvector long-term memory."""
    engine = get_memory_lifecycle_engine()
    res = engine.compress_conversation_history(
        organization_id=str(current_user.organization_id),
        conversation_id=payload.conversation_id,
        messages=payload.messages,
        message_threshold=payload.message_threshold
    )
    return res

@router.post("/gc")
async def trigger_garbage_collection(
    payload: GarbageCollectRequest,
    current_user: User = Depends(get_current_user),
):
    """Trigger memory GC: purge expired short-term records and move historical logs to cold storage."""
    engine = get_memory_lifecycle_engine()
    res = engine.run_garbage_collection(
        organization_id=str(current_user.organization_id),
        memory_records=payload.memory_records,
        retention_days=payload.retention_days
    )
    return res

@router.post("/rebuild-index")
async def rebuild_vector_index(current_user: User = Depends(get_current_user)):
    """Trigger HNSW vector index maintenance sweep for an organization."""
    engine = get_memory_lifecycle_engine()
    res = engine.trigger_hnsw_index_rebuild(str(current_user.organization_id))
    return res
