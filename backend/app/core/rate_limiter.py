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

class TokenBucketRateLimiter:
    """Enterprise Multi-Dimensional Redis Token Bucket Rate Limiting Engine."""

    def __init__(self):
        # Maps (dimension, identifier) -> TokenBucket
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

    def consume(
        self,
        dimension: RateLimitDimension,
        identifier: str,
        tokens_needed: float = 1.0
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Deduct token(s) from bucket after refilling based on elapsed time.
        Returns (allowed_bool, metadata_dict).
        """
        now = time.time()
        bucket = self._get_or_create_bucket(dimension, identifier)
        cfg = DIMENSION_CONFIGS[dimension]

        # Refill tokens based on elapsed time
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
                "retry_after_sec": 0
            }

        # Out of tokens - calculate retry delay
        missing = tokens_needed - bucket.tokens
        retry_after = max(1, int(missing / bucket.refill_rate))
        return False, {
            "allowed": False,
            "remaining": 0,
            "limit": cfg.rate_limit_per_min,
            "burst_limit": cfg.burst_limit,
            "retry_after_sec": retry_after
        }

    def get_headers(self, dimension: RateLimitDimension, identifier: str) -> Dict[str, str]:
        """Construct standard HTTP rate limit response headers."""
        allowed, meta = self.consume(dimension, identifier, tokens_needed=0.0) # non-destructive check
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
