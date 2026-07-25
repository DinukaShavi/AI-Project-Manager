import asyncio
import time
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.rate_limiter import (
    get_rate_limiter,
    TokenBucketRateLimiter,
    RateLimitDimension
)

async def test_rate_limiter_flow():
    print("Initializing Multi-Dimensional Rate Limiting Engine & Token Bucket validation tests...")
    limiter = get_rate_limiter()
    test_user_id = str(uuid.uuid4())
    test_llm_key = str(uuid.uuid4())

    # 1. Test Token Bucket Consumption & Refill
    print("\nTest 1: Testing Token Bucket consumption and refill logic...")
    allowed, meta = limiter.consume(RateLimitDimension.USER, test_user_id, tokens_needed=1.0)
    assert allowed is True
    assert meta["remaining"] == 99 # Burst limit 100 - 1 = 99 remaining
    print("SUCCESS: Token bucket consumed single token from burst capacity.")

    # 2. Test Quota Exhaustion & Retry-After Calculation
    print("\nTest 2: Testing LLM Call Bucket exhaustion (30 burst limit)...")
    # Consume all 30 tokens for LLM_CALL
    allowed_bulk, meta_bulk = limiter.consume(RateLimitDimension.LLM_CALL, test_llm_key, tokens_needed=30.0)
    assert allowed_bulk is True

    # 31st token request should be blocked!
    blocked, meta_blocked = limiter.consume(RateLimitDimension.LLM_CALL, test_llm_key, tokens_needed=1.0)
    assert blocked is False
    assert meta_blocked["remaining"] == 0
    assert meta_blocked["retry_after_sec"] >= 1
    print(f"SUCCESS: LLM_CALL rate limit exceeded. Retry after {meta_blocked['retry_after_sec']}s calculated.")

    # 3. Test HTTP Response Headers
    print("\nTest 3: Testing HTTP rate limit response header construction...")
    headers = limiter.get_headers(RateLimitDimension.USER, test_user_id)
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    print("SUCCESS: Rate limit HTTP headers constructed.")

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
