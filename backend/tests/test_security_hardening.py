import asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from starlette.testclient import TestClient

import app.db.base # Register models
from app.main import app
from app.core.security import sanitize_string
from app.core.middleware import RateLimitingMiddleware, SecurityHeadersMiddleware

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

    # 3. Test Rate Limiting Middleware Threshold
    print("\nTest 3: Testing IP rate limiting middleware threshold enforcement...")
    test_app = FastAPI()
    test_app.add_middleware(RateLimitingMiddleware, max_requests=3, window_seconds=60)
    
    @test_app.get("/api/test")
    async def sample_endpoint():
        return {"status": "ok"}

    sync_client = TestClient(test_app)

    # Requests 1, 2, 3 should succeed
    for i in range(1, 4):
        resp = sync_client.get("/api/test")
        assert resp.status_code == 200, f"Request {i} failed unexpectedly"

    # Request 4 should be rate limited with HTTP 429
    rate_limited_resp = sync_client.get("/api/test")
    assert rate_limited_resp.status_code == 429, f"Expected 429 rate limit, got {rate_limited_resp.status_code}"
    assert rate_limited_resp.json()["detail"] == "Too many requests. Please slow down."
    print("SUCCESS: HTTP 429 Too Many Requests returned upon exceeding rate threshold.")

    print("\nAll Security Hardening tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_security_hardening_flow())
