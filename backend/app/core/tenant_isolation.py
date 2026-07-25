from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional

class TenantIsolationViolationException(Exception):
    """Raised when cross-tenant access is attempted without authorized super-admin credentials."""
    pass

@dataclass
class TenantContext:
    tenant_id: str
    user_id: str
    is_super_admin: bool = False

class TenantIsolationEngine:
    """Enterprise Multi-Tenant Schema & Virtual Isolation Engine across DB, Redis, Queues & WebSockets."""

    def partition_redis_key(self, tenant_id: str, key: str) -> str:
        """Format Redis key with Tenant Namespace Isolation prefix: tenant:{id}:{key}."""
        if key.startswith(f"tenant:{tenant_id}:"):
            return key
        return f"tenant:{tenant_id}:{key}"

    def partition_routing_key(self, tenant_id: str, event_type: str) -> str:
        """Format Event Bus topic routing key with Tenant Isolation prefix: tenant.{id}.{event_type}."""
        if event_type.startswith(f"tenant.{tenant_id}."):
            return event_type
        return f"tenant.{tenant_id}.{event_type}"

    def partition_worker_queue(self, tenant_id: str, priority: str = "standard") -> str:
        """Assign isolated Celery worker queue for tenant resource protection."""
        if priority == "high":
            return f"tenant_{tenant_id}_dedicated_high_priority_queue"
        return f"tenant_{tenant_id}_shared_{priority}_queue"

    def partition_ws_channel(self, tenant_id: str, channel: str) -> str:
        """Format WebSocket channel name with Tenant Isolation namespace: ws:tenant:{id}:{channel}."""
        if channel.startswith(f"ws:tenant:{tenant_id}:"):
            return channel
        return f"ws:tenant:{tenant_id}:{channel}"

    def validate_vector_query_filter(
        self,
        tenant_id: str,
        query_filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Inject and enforce mandatory tenant_id namespace filtering in pgvector queries."""
        filt = dict(query_filter or {})
        filt["tenant_id"] = tenant_id
        filt["organization_id"] = tenant_id # fallback alias
        return filt

    def audit_cross_tenant_access(
        self,
        source_tenant_id: str,
        target_tenant_id: str,
        is_super_admin: bool = False
    ) -> Tuple[bool, str]:
        """
        Cross-Tenant Leak Auditor:
        Enforces strict multi-tenant boundary checks.
        Blocks cross-tenant operations unless performed by a verified super-admin.
        """
        if source_tenant_id == target_tenant_id:
            return True, "SAME_TENANT_ACCESS_ALLOWED"

        if is_super_admin:
            return True, "SUPER_ADMIN_AUDIT_PERMITTED"

        return False, f"TENANT_ISOLATION_VIOLATION: Tenant '{source_tenant_id}' denied access to Tenant '{target_tenant_id}' resource."


# Singleton Instance Manager
_tenant_isolation_engine_instance: Optional[TenantIsolationEngine] = None

def get_tenant_isolation_engine() -> TenantIsolationEngine:
    """Get global TenantIsolationEngine singleton instance."""
    global _tenant_isolation_engine_instance
    if _tenant_isolation_engine_instance is None:
        _tenant_isolation_engine_instance = TenantIsolationEngine()
    return _tenant_isolation_engine_instance
