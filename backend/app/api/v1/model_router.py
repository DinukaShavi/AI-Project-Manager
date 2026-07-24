from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.core.model_router import get_model_router, ROUTING_MATRIX

router = APIRouter(prefix="/models", tags=["Model Routing & Fallbacks"])

class ModelRouteRequest(BaseModel):
    task_category: str
    budget_tier: str = "standard"
    token_length: int = 1000

@router.get("/matrix")
async def get_routing_matrix():
    """Fetch active Model Routing Matrix configuration and pricing rates."""
    matrix_output = {}
    for cat, cfg in ROUTING_MATRIX.items():
        matrix_output[cat.value] = {
            "primary_model": cfg.primary_model,
            "fallback_model": cfg.fallback_model,
            "input_rate_per_1k_usd": cfg.input_rate_per_1k,
            "output_rate_per_1k_usd": cfg.output_rate_per_1k,
            "max_context_window": cfg.max_context_window,
            "selection_reason": cfg.selection_reason
        }
    return {"routing_matrix": matrix_output}

@router.post("/route")
async def select_model_route(payload: ModelRouteRequest):
    """Dynamically select primary and fallback model routes for a given task category."""
    router_engine = get_model_router()
    route = router_engine.select_model(
        task_category=payload.task_category,
        budget_tier=payload.budget_tier,
        token_length=payload.token_length
    )
    return route
