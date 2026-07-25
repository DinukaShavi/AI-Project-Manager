from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.core.rate_limiter import get_rate_limiter, RateLimitDimension

router = APIRouter(prefix="/rate-limit", tags=["Multi-Dimensional Rate Limiting"])

class ConsumeTokenRequest(BaseModel):
    dimension: str # user, organization, api_key, websocket, llm_call
    identifier: str
    tokens_needed: float = 1.0

@router.post("/check")
async def check_rate_limit(payload: ConsumeTokenRequest, response: Response):
    """Check and consume tokens from the token bucket for a specified dimension and identifier."""
    limiter = get_rate_limiter()
    try:
        dim_enum = RateLimitDimension(payload.dimension.lower())
    except ValueError:
        dim_enum = RateLimitDimension.USER

    allowed, meta = limiter.consume(dim_enum, payload.identifier, payload.tokens_needed)
    
    response.headers["X-RateLimit-Limit"] = str(meta["limit"])
    response.headers["X-RateLimit-Remaining"] = str(meta["remaining"])
    
    if not allowed:
        response.headers["Retry-After"] = str(meta["retry_after_sec"])
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for dimension '{payload.dimension}'. Retry after {meta['retry_after_sec']} seconds.",
            headers={"Retry-After": str(meta["retry_after_sec"])}
        )

    return meta

@router.get("/status/{dimension}/{identifier}")
async def get_bucket_status(dimension: str, identifier: str):
    """Fetch current bucket capacity and remaining token count."""
    limiter = get_rate_limiter()
    try:
        dim_enum = RateLimitDimension(dimension.lower())
    except ValueError:
        dim_enum = RateLimitDimension.USER

    _, meta = limiter.consume(dim_enum, identifier, tokens_needed=0.0)
    return meta
