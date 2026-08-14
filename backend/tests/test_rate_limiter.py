import asyncio
import time
import uuid
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.rate_limiter import (
    get_rate_limiter,
    TokenBucketRateLimiter,
    RateLimitDimension,
)

async def test_rate_limiter_flow():
    print("Initializing Multi-Dimensional Rate Limiting Engine & Token Bucket validation tests...")
    limiter = get_rate_limiter()
    test_user_id = str(uuid.uuid4())
    test_llm_key = str(uuid.uuid4())

    # 1. Test Token Bucket Consumption & Refill (in-memory fallback path — no local Redis is
    # reachable in this environment, matching every other Redis-backed feature in this codebase,
    # e.g. DistributedLockManager / RedisEventBus, which fall back the same way).
    print("\nTest 1: Testing Token Bucket consumption and refill logic (in-memory fallback)...")
    allowed, meta = await limiter.consume(RateLimitDimension.USER, test_user_id, tokens_needed=1.0)
    assert allowed is True
    assert meta["remaining"] == 99 # Burst limit 100 - 1 = 99 remaining
    assert meta["backend"] == "in_memory"
    print("SUCCESS: Token bucket consumed single token from burst capacity via the in-memory fallback.")

    # 2. Test Quota Exhaustion & Retry-After Calculation
    print("\nTest 2: Testing LLM Call Bucket exhaustion (30 burst limit)...")
    # Consume all 30 tokens for LLM_CALL
    allowed_bulk, meta_bulk = await limiter.consume(RateLimitDimension.LLM_CALL, test_llm_key, tokens_needed=30.0)
    assert allowed_bulk is True

    # 31st token request should be blocked!
    blocked, meta_blocked = await limiter.consume(RateLimitDimension.LLM_CALL, test_llm_key, tokens_needed=1.0)
    assert blocked is False
    assert meta_blocked["remaining"] == 0
    assert meta_blocked["retry_after_sec"] >= 1
    print(f"SUCCESS: LLM_CALL rate limit exceeded. Retry after {meta_blocked['retry_after_sec']}s calculated.")

    # 3. Test HTTP Response Headers
    print("\nTest 3: Testing HTTP rate limit response header construction...")
    headers = await limiter.get_headers(RateLimitDimension.USER, test_user_id)
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    print("SUCCESS: Rate limit HTTP headers constructed.")

    # 3b. Test the Redis-backed path (mocked — engineering_handbook.md's testing pyramid calls
    # for mocking externals unit-test-side; no local Redis is reachable here to test against for
    # real, same limitation as test_distributed_lock.py). Proves the Lua script is invoked with
    # the correct arguments and that its [allowed, remaining] reply is parsed correctly.
    print("\nTest 3b: Testing the Redis-backed token bucket path against a mocked Redis client...")
    fresh_limiter = TokenBucketRateLimiter()
    mock_redis_client = AsyncMock()
    mock_redis_client.eval.return_value = [1, "42.5"]  # allowed=True, 42.5 tokens remaining

    class _FakeEventBus:
        client = mock_redis_client

    with patch("app.events.redis_bus.get_event_bus", return_value=_FakeEventBus()):
        allowed_redis, meta_redis = await fresh_limiter.consume(RateLimitDimension.API_KEY, "redis-test-key", tokens_needed=1.0)

    assert allowed_redis is True
    assert meta_redis["backend"] == "redis"
    assert meta_redis["remaining"] == 42
    assert mock_redis_client.eval.await_count == 1
    call_args = mock_redis_client.eval.await_args
    assert call_args[0][0].strip().startswith("local key = KEYS[1]")  # the Lua script itself
    assert call_args[0][2] == f"ratelimit:api_key:redis-test-key"  # KEYS[1]
    print("SUCCESS: Redis-backed path correctly invoked the Lua token-bucket script and parsed its reply.")

    # 3c. Test graceful fallback when the Redis call itself fails (e.g. connection drop).
    print("\nTest 3c: Testing fallback to in-memory when a present Redis client errors out...")
    failing_redis_client = AsyncMock()
    failing_redis_client.eval.side_effect = ConnectionError("Redis connection lost")

    class _FailingEventBus:
        client = failing_redis_client

    with patch("app.events.redis_bus.get_event_bus", return_value=_FailingEventBus()):
        allowed_fallback, meta_fallback = await fresh_limiter.consume(RateLimitDimension.API_KEY, "redis-fail-key", tokens_needed=1.0)
    assert allowed_fallback is True
    assert meta_fallback["backend"] == "in_memory"
    print("SUCCESS: A failing Redis call correctly degraded to the in-memory bucket instead of raising.")

    # 4. Test REST API Endpoints & HTTP 429 Status Code
    print("\nTest 4: Testing Rate Limiter HTTP REST API endpoints & 429 responses...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/v1/rate-limit/status/user/{test_user_id}
        res_stat = await client.get(f"/api/v1/rate-limit/status/user/{test_user_id}")
        assert res_stat.status_code == 200
        assert res_stat.json()["limit"] == 60

        # POST /api/v1/rate-limit/check (exhaust api_key dimension)
        api_key_id = str(uuid.uuid4())
        # Exhaust 200 tokens
        await client.post(
            "/api/v1/rate-limit/check",
            json={"dimension": "api_key", "identifier": api_key_id, "tokens_needed": 200.0}
        )
        # Next call triggers 429
        res_blocked = await client.post(
            "/api/v1/rate-limit/check",
            json={"dimension": "api_key", "identifier": api_key_id, "tokens_needed": 1.0}
        )
        assert res_blocked.status_code == 429
        assert "Retry-After" in res_blocked.headers
        print("SUCCESS: Rate Limiter REST API returned HTTP 429 with Retry-After header.")

    print("\nAll Multi-Dimensional Rate Limiting Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_rate_limiter_flow())
