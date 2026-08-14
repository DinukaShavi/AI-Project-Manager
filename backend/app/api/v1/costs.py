from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.api.deps import get_current_user
from app.models.tenant import User
from app.services.cost_monitoring import get_cost_monitoring_service

router = APIRouter(prefix="/costs", tags=["AI Cost Monitoring & Budgets"])

class RecordUsageRequest(BaseModel):
    agent_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int = 0

@router.post("/record", status_code=status.HTTP_201_CREATED)
async def record_token_usage(
    payload: RecordUsageRequest,
    current_user: User = Depends(get_current_user)
):
    """Log LLM token usage metrics and calculate USD expenditure, scoped to the
    authenticated caller's own organization/user -- never a client-supplied identity."""
    service = get_cost_monitoring_service()
    rec = service.record_usage(
        organization_id=str(current_user.organization_id),
        user_id=str(current_user.id),
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
async def get_cost_summary(
    organization_id: str,
    current_user: User = Depends(get_current_user)
):
    """Fetch aggregated token consumption metrics, total USD spend, and breakdown by
    agent & model. The path organization_id must match the authenticated caller's own
    organization (same explicit-ownership-check convention already established in
    integrations.py's GET /oauth/tokens/{organization_id}) -- it is never trusted as the
    tenant authority on its own."""
    if organization_id != str(current_user.organization_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access another organization's cost data.")
    service = get_cost_monitoring_service()
    return service.get_organization_cost_summary(organization_id)

@router.get("/alerts/{organization_id}")
async def check_budget_alerts(
    organization_id: str,
    monthly_budget_usd: float = 100.0,
    current_user: User = Depends(get_current_user)
):
    """Check budget alerts and threshold breaches for an organization. Same explicit
    ownership check as get_cost_summary."""
    if organization_id != str(current_user.organization_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access another organization's cost data.")
    service = get_cost_monitoring_service()
    return service.check_budget_alert(organization_id, monthly_budget_usd)
