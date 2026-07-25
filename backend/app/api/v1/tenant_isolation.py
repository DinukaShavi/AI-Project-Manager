from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.core.tenant_isolation import get_tenant_isolation_engine

router = APIRouter(prefix="/tenants", tags=["Multi-Tenant Isolation Strategy"])

class PartitionKeysRequest(BaseModel):
    tenant_id: str
    key: str
    event_type: str
    channel: str
    priority: Optional[str] = "standard"

class VectorQueryFilterRequest(BaseModel):
    tenant_id: str
    query_filter: Optional[Dict[str, Any]] = None

class AuditAccessRequest(BaseModel):
    source_tenant_id: str
    target_tenant_id: str
    is_super_admin: bool = False

@router.post("/partition-keys")
async def partition_tenant_keys(payload: PartitionKeysRequest):
    """Generate isolated tenant namespace keys across Redis, Event Bus, Queues, and WebSockets."""
    engine = get_tenant_isolation_engine()
    return {
        "tenant_id": payload.tenant_id,
        "redis_key": engine.partition_redis_key(payload.tenant_id, payload.key),
        "event_routing_key": engine.partition_routing_key(payload.tenant_id, payload.event_type),
        "worker_queue": engine.partition_worker_queue(payload.tenant_id, payload.priority or "standard"),
        "websocket_channel": engine.partition_ws_channel(payload.tenant_id, payload.channel)
    }

@router.post("/validate-vector-query")
async def validate_vector_query(payload: VectorQueryFilterRequest):
    """Inject mandatory tenant_id filter into pgvector similarity queries."""
    engine = get_tenant_isolation_engine()
    enforced_filter = engine.validate_vector_query_filter(payload.tenant_id, payload.query_filter)
    return {
        "tenant_id": payload.tenant_id,
        "enforced_vector_filter": enforced_filter
    }

@router.post("/audit-access")
async def audit_cross_tenant_access(payload: AuditAccessRequest):
    """Audit cross-tenant access requests and enforce multi-tenant isolation boundaries."""
    engine = get_tenant_isolation_engine()
    allowed, message = engine.audit_cross_tenant_access(
        payload.source_tenant_id,
        payload.target_tenant_id,
        payload.is_super_admin
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message
        )
    return {
        "allowed": True,
        "status": message
    }
