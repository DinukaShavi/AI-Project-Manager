import asyncio
import uuid
import time
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from app.core.config import settings
from app.events.redis_bus import get_event_bus

# Lua script for atomic lock release (only releases if token matches)
RELEASE_LUA_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Lua script for atomic lease extension (only extends if token matches)
EXTEND_LUA_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""

class DistributedLockManager:
    """Redis-backed Redlock Distributed Lock Manager with 30s TTL and automatic background lease renewal."""

    def __init__(self):
        self._in_memory_locks: Dict[str, Dict[str, Any]] = {}

    async def acquire_lock(
        self,
        resource_key: str,
        ttl_seconds: int = 30
    ) -> Optional[str]:
        """Acquire a distributed lock for a resource key returning a unique token if granted."""
        lock_token = str(uuid.uuid4())
        full_key = f"lock:{resource_key}"
        ttl_ms = int(ttl_seconds * 1000)

        event_bus = get_event_bus()
        if hasattr(event_bus, "client") and event_bus.client:
            # Native Redis SET key token NX PX ttl_ms
            try:
                acquired = await event_bus.client.set(full_key, lock_token, nx=True, px=ttl_ms)
                if acquired:
                    return lock_token
                return None
            except Exception:
                pass # Fallback to in-memory lock store below

        # Fallback In-Memory Lock Manager
        now = time.time()
        existing = self._in_memory_locks.get(full_key)
        if existing and existing["expires_at"] > now:
            return None # Locked by another process

        self._in_memory_locks[full_key] = {
            "token": lock_token,
            "expires_at": now + ttl_seconds
        }
        return lock_token

    async def release_lock(
        self,
        resource_key: str,
        lock_token: str
    ) -> bool:
        """Atomically release a distributed lock if the token matches."""
        full_key = f"lock:{resource_key}"

        event_bus = get_event_bus()
        if hasattr(event_bus, "client") and event_bus.client:
            try:
                res = await event_bus.client.eval(RELEASE_LUA_SCRIPT, 1, full_key, lock_token)
                return bool(res)
            except Exception:
                pass

        # Fallback In-Memory Release
        existing = self._in_memory_locks.get(full_key)
        if existing and existing["token"] == lock_token:
            del self._in_memory_locks[full_key]
            return True
        return False

    async def extend_lease(
        self,
        resource_key: str,
        lock_token: str,
        ttl_seconds: int = 30
    ) -> bool:
        """Extend lock lease TTL for long-running worker operations."""
        full_key = f"lock:{resource_key}"
        ttl_ms = int(ttl_seconds * 1000)

        event_bus = get_event_bus()
        if hasattr(event_bus, "client") and event_bus.client:
            try:
                res = await event_bus.client.eval(EXTEND_LUA_SCRIPT, 1, full_key, lock_token, ttl_ms)
                return bool(res)
            except Exception:
                pass

        # Fallback In-Memory Extension
        existing = self._in_memory_locks.get(full_key)
        if existing and existing["token"] == lock_token:
            existing["expires_at"] = time.time() + ttl_seconds
            return True
        return False

    @asynccontextmanager
    async def lock(
        self,
        resource_key: str,
        ttl_seconds: int = 30,
        retry_delay_seconds: float = 0.2,
        max_wait_seconds: float = 5.0,
        auto_renew: bool = True
    ):
        """Async context manager acquiring lock, running background lease renewer, and auto-releasing on exit."""
        start_time = time.time()
        token = None

        # Acquisition retry loop
        while time.time() - start_time < max_wait_seconds:
            token = await self.acquire_lock(resource_key, ttl_seconds)
            if token:
                break
            await asyncio.sleep(retry_delay_seconds)

        if not token:
            raise TimeoutError(f"Could not acquire distributed lock for resource '{resource_key}' within {max_wait_seconds}s.")

        renew_task = None
        if auto_renew:
            async def renew_loop():
                renew_interval = max(1.0, ttl_seconds / 3.0)
                try:
                    while True:
                        await asyncio.sleep(renew_interval)
                        await self.extend_lease(resource_key, token, ttl_seconds)
                except asyncio.CancelledError:
                    pass

            renew_task = asyncio.create_task(renew_loop())

        try:
            yield token
        finally:
            if renew_task:
                renew_task.cancel()
                try:
                    await renew_task
                except asyncio.CancelledError:
                    pass
            await self.release_lock(resource_key, token)


# Singleton Instance Manager
_lock_manager_instance: Optional[DistributedLockManager] = None

def get_lock_manager() -> DistributedLockManager:
    """Get global DistributedLockManager singleton."""
    global _lock_manager_instance
    if _lock_manager_instance is None:
        _lock_manager_instance = DistributedLockManager()
    return _lock_manager_instance
