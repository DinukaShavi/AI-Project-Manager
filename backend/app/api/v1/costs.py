from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.services.cost_monitoring import get_cost_monitoring_service

router = APIRouter(prefix="/costs", tags=["AI Cost Monitoring & Budgets"])

class RecordUsageRequest(BaseModel):
    organization_id: str
    user_id: str
    agent_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int = 0

@router.post("/record", status_code=status.HTTP_201_CREATED)
async def record_token_usage(payload: RecordUsageRequest):
    """Log LLM token usage metrics and calculate USD expenditure."""
    service = get_cost_monitoring_service()
    rec = service.record_usage(
        organization_id=payload.organization_id,
        user_id=payload.user_id,
        agent_name=payload.agent_name,
        model=payload.model,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        cache_hit_tokens=payload.cache_hit_tokens
    )
    return {
        "message": "Token usage logged successfully.",
        "record": {
            "organization_id": rec.organization_id,
            "agent_name": rec.agent_name,
            "model": rec.model,
            "prompt_tokens": rec.prompt_tokens,
            "completion_tokens": rec.completion_tokens,
            "cache_hit_tokens": rec.cache_hit_tokens,
            "cost_usd": rec.cost_usd
        }
    }

@router.get("/summary/{organization_id}")
async def get_cost_summary(organization_id: str):
    """Fetch aggregated token consumption metrics, total USD spend, and breakdown by agent & model."""
    service = get_cost_monitoring_service()
    return service.get_organization_cost_summary(organization_id)

@router.get("/alerts/{organization_id}")
async def check_budget_alerts(organization_id: str, monthly_budget_usd: float = 100.0):
    """Check budget alerts and threshold breaches for an organization."""
    service = get_cost_monitoring_service()
    return service.check_budget_alert(organization_id, monthly_budget_usd)
