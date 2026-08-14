import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Tuple, Any, Optional

class RateLimitDimension(str, Enum):
    USER = "user"
    ORGANIZATION = "organization"
    API_KEY = "api_key"
    WEBSOCKET = "websocket"
    LLM_CALL = "llm_call"

@dataclass
class BucketConfig:
    rate_limit_per_min: int
    refill_rate_per_sec: float
    burst_limit: int

DIMENSION_CONFIGS: Dict[RateLimitDimension, BucketConfig] = {
    RateLimitDimension.USER: BucketConfig(60, 1.0, 100),
    RateLimitDimension.ORGANIZATION: BucketConfig(600, 10.0, 1000),
    RateLimitDimension.API_KEY: BucketConfig(120, 2.0, 200),
    RateLimitDimension.WEBSOCKET: BucketConfig(100, 1.6, 150),
    RateLimitDimension.LLM_CALL: BucketConfig(20, 0.33, 30),
}

@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float
    tokens: float
    last_refill: float = field(default_factory=time.time)

# Atomic Redis-side token bucket refill + consume, mirroring the exact algorithm used by the
# in-memory fallback below: refill by elapsed-time * rate up to capacity, then consume if enough
# tokens are available. Executed as a single Lua script (same pattern as
# app.core.distributed_lock's RELEASE/EXTEND scripts) so concurrent requests across multiple
# worker processes see a consistent, race-free bucket state instead of each process keeping
# its own independent in-memory count.
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local tokens_needed = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttl_seconds = tonumber(ARGV[5])

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = now - last_refill
if elapsed > 0 then
    tokens = math.min(capacity, tokens + (elapsed * refill_rate))
end

local allowed = 0
if tokens >= tokens_needed then
    tokens = tokens - tokens_needed
    allowed = 1
end

redis.call("HMSET", key, "tokens", tostring(tokens), "last_refill", tostring(now))
redis.call("EXPIRE", key, ttl_seconds)

return {allowed, tostring(tokens)}
"""


class TokenBucketRateLimiter:
    """Enterprise Multi-Dimensional Token Bucket Rate Limiting Engine.

    Backed by Redis (atomic Lua script, shared across all worker processes) when
    settings.USE_REDIS is enabled and reachable; otherwise falls back to an in-process
    dict, matching the same fallback pattern already used by
    app.core.distributed_lock.DistributedLockManager and app.events.redis_bus.
    """

    def __init__(self):
        # In-memory fallback store: (dimension, identifier) -> TokenBucket
        self.buckets: Dict[Tuple[str, str], TokenBucket] = {}

    def _get_or_create_bucket(self, dimension: RateLimitDimension, identifier: str) -> TokenBucket:
        key = (dimension.value, identifier)
        if key not in self.buckets:
            cfg = DIMENSION_CONFIGS[dimension]
            self.buckets[key] = TokenBucket(
                capacity=float(cfg.burst_limit),
                refill_rate=cfg.refill_rate_per_sec,
                tokens=float(cfg.burst_limit),
                last_refill=time.time()
            )
        return self.buckets[key]

    def _consume_in_memory(
        self,
        dimension: RateLimitDimension,
        identifier: str,
        tokens_needed: float
    ) -> Tuple[bool, Dict[str, Any]]:
        now = time.time()
        bucket = self._get_or_create_bucket(dimension, identifier)
        cfg = DIMENSION_CONFIGS[dimension]

        elapsed = now - bucket.last_refill
        bucket.tokens = min(bucket.capacity, bucket.tokens + (elapsed * bucket.refill_rate))
        bucket.last_refill = now

        if bucket.tokens >= tokens_needed:
            bucket.tokens -= tokens_needed
            return True, {
                "allowed": True,
                "remaining": int(bucket.tokens),
                "limit": cfg.rate_limit_per_min,
                "burst_limit": cfg.burst_limit,
                "retry_after_sec": 0,
                "backend": "in_memory",
            }

        missing = tokens_needed - bucket.tokens
        # A dimension configured with no refill (burst-once policy) never regains tokens,
        # so there's no finite wait to report -- fall back to a fixed cooldown hint
        # rather than dividing by zero.
        retry_after = max(1, int(missing / bucket.refill_rate)) if bucket.refill_rate > 0 else 3600
        return False, {
            "allowed": False,
            "remaining": 0,
            "limit": cfg.rate_limit_per_min,
            "burst_limit": cfg.burst_limit,
            "retry_after_sec": retry_after,
            "backend": "in_memory",
        }

    async def _consume_redis(
        self,
        redis_client,
        dimension: RateLimitDimension,
        identifier: str,
        tokens_needed: float
    ) -> Tuple[bool, Dict[str, Any]]:
        cfg = DIMENSION_CONFIGS[dimension]
        key = f"ratelimit:{dimension.value}:{identifier}"

        allowed_flag, remaining_str = await redis_client.eval(
            _TOKEN_BUCKET_LUA,
            1,
            key,
            float(cfg.burst_limit),
            cfg.refill_rate_per_sec,
            tokens_needed,
            time.time(),
            3600,  # bucket key TTL — well beyond any realistic idle gap between requests
        )
        allowed = bool(int(allowed_flag))
        remaining = int(float(remaining_str))

        if allowed:
            return True, {
                "allowed": True,
                "remaining": remaining,
                "limit": cfg.rate_limit_per_min,
                "burst_limit": cfg.burst_limit,
                "retry_after_sec": 0,
                "backend": "redis",
            }

        missing = tokens_needed - remaining
        retry_after = max(1, int(missing / cfg.refill_rate_per_sec)) if cfg.refill_rate_per_sec > 0 else 3600
        return False, {
            "allowed": False,
            "remaining": 0,
            "limit": cfg.rate_limit_per_min,
            "burst_limit": cfg.burst_limit,
            "retry_after_sec": retry_after,
            "backend": "redis",
        }

    async def consume(
        self,
        dimension: RateLimitDimension,
        identifier: str,
        tokens_needed: float = 1.0
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Deduct token(s) from the dimension/identifier bucket, refilling based on elapsed time.
        Returns (allowed_bool, metadata_dict). Prefers Redis for cross-process consistency;
        falls back to the in-memory bucket if Redis is disabled or unreachable.
        """
        from app.events.redis_bus import get_event_bus

        event_bus = get_event_bus()
        if getattr(event_bus, "client", None):
            try:
                return await self._consume_redis(event_bus.client, dimension, identifier, tokens_needed)
            except Exception:
                pass  # Fall through to the in-memory bucket below

        return self._consume_in_memory(dimension, identifier, tokens_needed)

    async def get_headers(self, dimension: RateLimitDimension, identifier: str) -> Dict[str, str]:
        """Construct standard HTTP rate limit response headers."""
        allowed, meta = await self.consume(dimension, identifier, tokens_needed=0.0) # non-destructive check
        headers = {
            "X-RateLimit-Limit": str(meta["limit"]),
            "X-RateLimit-Remaining": str(meta["remaining"])
        }
        if not allowed:
            headers["Retry-After"] = str(meta["retry_after_sec"])
        return headers


# Singleton Instance Manager
_rate_limiter_instance: Optional[TokenBucketRateLimiter] = None

def get_rate_limiter() -> TokenBucketRateLimiter:
    """Get global TokenBucketRateLimiter singleton instance."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = TokenBucketRateLimiter()
    return _rate_limiter_instance
