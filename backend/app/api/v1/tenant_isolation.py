from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.api.deps import get_current_user
from app.models.tenant import User
from app.core.rbac_pdp import UserRole
from app.core.tenant_isolation import get_tenant_isolation_engine

router = APIRouter(prefix="/tenants", tags=["Multi-Tenant Isolation Strategy"])

class PartitionKeysRequest(BaseModel):
    key: str
    event_type: str
    channel: str
    priority: Optional[str] = "standard"

class VectorQueryFilterRequest(BaseModel):
    query_filter: Optional[Dict[str, Any]] = None

class AuditAccessRequest(BaseModel):
    target_tenant_id: str

@router.post("/partition-keys")
async def partition_tenant_keys(
    payload: PartitionKeysRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate isolated tenant namespace keys across Redis, Event Bus, Queues, and WebSockets
    for the caller's own real organization."""
    tenant_id = str(current_user.organization_id)
    engine = get_tenant_isolation_engine()
    return {
        "tenant_id": tenant_id,
        "redis_key": engine.partition_redis_key(tenant_id, payload.key),
        "event_routing_key": engine.partition_routing_key(tenant_id, payload.event_type),
        "worker_queue": engine.partition_worker_queue(tenant_id, payload.priority or "standard"),
        "websocket_channel": engine.partition_ws_channel(tenant_id, payload.channel)
    }

@router.post("/validate-vector-query")
async def validate_vector_query(
    payload: VectorQueryFilterRequest,
    current_user: User = Depends(get_current_user),
):
    """Inject mandatory tenant_id filter into pgvector similarity queries, scoped to the
    caller's own real organization."""
    tenant_id = str(current_user.organization_id)
    engine = get_tenant_isolation_engine()
    enforced_filter = engine.validate_vector_query_filter(tenant_id, payload.query_filter)
    return {
        "tenant_id": tenant_id,
        "enforced_vector_filter": enforced_filter
    }

@router.post("/audit-access")
async def audit_cross_tenant_access(
    payload: AuditAccessRequest,
    current_user: User = Depends(get_current_user),
):
    """Audit whether the real caller may access a target tenant's resources. `is_super_admin`
    is never client-supplied -- it's derived from the real authenticated user's real roles,
    since this endpoint's entire purpose is enforcing that boundary."""
    source_tenant_id = str(current_user.organization_id)
    is_super_admin = UserRole.SUPER_ADMIN.value in {r.name for r in current_user.roles}

    engine = get_tenant_isolation_engine()
    allowed, message = engine.audit_cross_tenant_access(
        source_tenant_id,
        payload.target_tenant_id,
        is_super_admin,
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
