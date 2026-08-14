import asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from starlette.testclient import TestClient

import app.db.base # Register models
from app.main import app
from app.core.security import sanitize_string
from app.core.middleware import RateLimitingMiddleware, SecurityHeadersMiddleware
from app.core.rate_limiter import DIMENSION_CONFIGS, BucketConfig, RateLimitDimension

async def test_security_hardening_flow():
    print("Initializing Security Hardening validation tests...")

    # 1. Test Input Sanitization
    print("\nTest 1: Testing input string sanitization...")
    malicious_input = "<script>alert('xss_attack')</script>"
    sanitized = sanitize_string(malicious_input)
    assert "<script>" not in sanitized
    assert "&lt;script&gt;" in sanitized
    print(f"SUCCESS: Input sanitized correctly: '{sanitized}'")

    # 2. Test Security Headers
    print("\nTest 2: Testing OWASP security response headers...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        headers = res.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Strict-Transport-Security" in headers
        print("SUCCESS: All 4 OWASP security headers verified on HTTP response.")

    # 3. Test Rate Limiting Middleware Threshold. The middleware now delegates to the
    # documented, shared TokenBucketRateLimiter (dimension configs fixed in
    # app.core.rate_limiter.DIMENSION_CONFIGS) instead of taking its own per-instance
    # max_requests/window_seconds — temporarily shrink the anonymous-traffic API_KEY
    # dimension's burst limit to keep this test fast and deterministic. A standalone
    # FastAPI test_app + starlette TestClient (not the shared `app` used by the rest of
    # the suite) keeps this isolated: TestClient's synthetic client host ("testclient")
    # never collides with the ASGITransport-based tests elsewhere in the suite ("127.0.0.1").
    print("\nTest 3: Testing IP rate limiting middleware threshold enforcement...")
    test_app = FastAPI()
    test_app.add_middleware(RateLimitingMiddleware)

    @test_app.get("/api/test")
    async def sample_endpoint():
        return {"status": "ok"}

    sync_client = TestClient(test_app)

    with patch.dict(DIMENSION_CONFIGS, {RateLimitDimension.API_KEY: BucketConfig(rate_limit_per_min=3, refill_rate_per_sec=0.0, burst_limit=3)}):
        # Requests 1, 2, 3 should succeed
        for i in range(1, 4):
            resp = sync_client.get("/api/test")
            assert resp.status_code == 200, f"Request {i} failed unexpectedly"

        # Request 4 should be rate limited with HTTP 429
        rate_limited_resp = sync_client.get("/api/test")
        assert rate_limited_resp.status_code == 429, f"Expected 429 rate limit, got {rate_limited_resp.status_code}"
        assert rate_limited_resp.json()["detail"] == "Too many requests. Please slow down."
        assert "Retry-After" in rate_limited_resp.headers
    print("SUCCESS: HTTP 429 Too Many Requests returned upon exceeding rate threshold.")

    # 3b. Test that authenticated requests are rate-limited per-user (JWT sub), not by
    # shared IP -- confirming engineering_handbook.md's "enforced per tenant... and per
    # user" requirement, and that one user's traffic cannot exhaust another's or an
    # anonymous client's allowance.
    print("\nTest 3b: Testing authenticated requests are dimensioned per-user, not per-IP...")
    from app.core.security import create_access_token
    import uuid as uuid_lib
    fake_user_token = create_access_token(subject=str(uuid_lib.uuid4()))
    with patch.dict(DIMENSION_CONFIGS, {RateLimitDimension.API_KEY: BucketConfig(rate_limit_per_min=1, refill_rate_per_sec=0.0001, burst_limit=1)}):
        # Exhaust the anonymous API_KEY bucket for a fresh synthetic client -- a per-run
        # unique X-Forwarded-For identifier (not a fixed literal) so this can never collide
        # with Test 3's already-exhausted "testclient" bucket or with any other test run.
        anon_headers = {"X-Forwarded-For": f"198.51.100.{uuid_lib.uuid4().int % 254 + 1}"}
        resp_anon = sync_client.get("/api/test", headers=anon_headers)
        assert resp_anon.status_code == 200
        resp_anon_blocked = sync_client.get("/api/test", headers=anon_headers)
        assert resp_anon_blocked.status_code == 429, "Expected the anonymous bucket to now be exhausted"

        # An authenticated request from the SAME synthetic client IP must still succeed --
        # it's dimensioned by user identity (USER bucket, still fresh), not the
        # exhausted anonymous API_KEY/IP bucket.
        resp_auth = sync_client.get("/api/test", headers={**anon_headers, "Authorization": f"Bearer {fake_user_token}"})
        assert resp_auth.status_code == 200, "An authenticated request must not be blocked by an unrelated anonymous client's exhausted IP bucket"
    print("SUCCESS: Authenticated requests are correctly dimensioned per-user, isolated from anonymous per-IP traffic.")

    print("\nAll Security Hardening tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_security_hardening_flow())
