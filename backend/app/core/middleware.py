from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware injecting OWASP recommended security headers on all HTTP responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing the documented multi-dimensional rate limiting policy
    (engineering_handbook.md: "Rate limits are enforced per tenant... and per user...
    using Redis token buckets"; enterprise_ai_architecture_spec.md section 12's Multi-
    Dimensional Limits table). Delegates to the existing TokenBucketRateLimiter
    (app.core.rate_limiter, already built and tested for Phase 15c) instead of tracking
    its own ad hoc state, so limits are Redis-backed and consistent across worker
    processes/pods rather than trapped in a single process's memory.

    Authenticated requests are rate-limited per-user (JWT `sub`, dimension USER) so one
    user's traffic can never exhaust another user's or tenant's allowance. Requests with
    no resolvable user identity yet (login, registration, provider webhooks) fall back
    to the API_KEY dimension keyed by client IP -- resolved from X-Forwarded-For when
    present, since the documented deployment topology (implementation_roadmap.md:
    NGINX/AWS ALB blue/green) puts a load balancer in front of every real request, and
    trusting request.client.host directly would collapse every real end user behind
    that proxy into a single shared bucket.
    """

    def _resolve_identity(self, request: Request):
        from app.core.rate_limiter import RateLimitDimension
        from app.core.security import decode_token

        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            payload = decode_token(auth_header[7:].strip())
            if payload and payload.get("type") == "access" and payload.get("sub"):
                return RateLimitDimension.USER, str(payload["sub"])

        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host
        else:
            client_ip = "unknown"
        return RateLimitDimension.API_KEY, client_ip

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Bypass rate limiting for health check endpoint
        if request.url.path == "/health":
            return await call_next(request)

        from app.core.rate_limiter import get_rate_limiter

        dimension, identifier = self._resolve_identity(request)
        allowed, meta = await get_rate_limiter().consume(dimension, identifier, tokens_needed=1.0)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(meta["retry_after_sec"])}
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(meta["limit"])
        response.headers["X-RateLimit-Remaining"] = str(meta["remaining"])
        return response
