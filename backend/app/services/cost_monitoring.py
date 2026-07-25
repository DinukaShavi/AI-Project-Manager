import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

MODEL_RATES = {
    "claude-3-5-sonnet": {"input_rate": 0.003, "output_rate": 0.015, "cache_rate": 0.0015},
    "gpt-4o": {"input_rate": 0.005, "output_rate": 0.015, "cache_rate": 0.0025},
    "gemini-1-5-flash": {"input_rate": 0.00035, "output_rate": 0.00105, "cache_rate": 0.00017},
    "llama-3-8b": {"input_rate": 0.0001, "output_rate": 0.0002, "cache_rate": 0.00005},
    "text-embedding-3-small": {"input_rate": 0.00002, "output_rate": 0.0, "cache_rate": 0.0}
}

@dataclass
class TokenUsageRecord:
    organization_id: str
    user_id: str
    agent_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int
    cost_usd: float
    timestamp: float = field(default_factory=time.time)

class CostMonitoringService:
    """Enterprise AI Cost Monitoring, Token Accounting & Budget Alert Engine."""

    def __init__(self):
        # In-memory token usage repository (maps org_id -> List[TokenUsageRecord])
        self.usage_ledger: Dict[str, List[TokenUsageRecord]] = {}

    def calculate_call_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_hit_tokens: int = 0
    ) -> float:
        """
        Calculate total cost USD:
        Cost = (Prompt Tokens * Rate_input) + (Completion Tokens * Rate_output) - (Cache Hit Tokens * Rate_cache)
        """
        rates = MODEL_RATES.get(model.lower(), MODEL_RATES["claude-3-5-sonnet"])
        input_cost = (prompt_tokens / 1000.0) * rates["input_rate"]
        output_cost = (completion_tokens / 1000.0) * rates["output_rate"]
        cache_savings = (cache_hit_tokens / 1000.0) * rates["cache_rate"]

        total = max(0.0, input_cost + output_cost - cache_savings)
        return round(total, 6)

    def record_usage(
        self,
        organization_id: str,
        user_id: str,
        agent_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_hit_tokens: int = 0
    ) -> TokenUsageRecord:
        """Log LLM API call token metrics and USD expenditure."""
        cost = self.calculate_call_cost(model, prompt_tokens, completion_tokens, cache_hit_tokens)
        record = TokenUsageRecord(
            organization_id=organization_id,
            user_id=user_id,
            agent_name=agent_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cost_usd=cost
        )
        if organization_id not in self.usage_ledger:
            self.usage_ledger[organization_id] = []
        self.usage_ledger[organization_id].append(record)
        return record

    def get_organization_cost_summary(self, organization_id: str) -> Dict[str, Any]:
        """Aggregate token consumption metrics, total USD spend, and breakdown by agent & model."""
        records = self.usage_ledger.get(organization_id, [])

        total_prompt_tokens = sum(r.prompt_tokens for r in records)
        total_completion_tokens = sum(r.completion_tokens for r in records)
        total_cache_hits = sum(r.cache_hit_tokens for r in records)
        total_cost_usd = sum(r.cost_usd for r in records)

        by_agent: Dict[str, float] = {}
        by_model: Dict[str, float] = {}

        for r in records:
            by_agent[r.agent_name] = by_agent.get(r.agent_name, 0.0) + r.cost_usd
            by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd

        return {
            "organization_id": organization_id,
            "total_calls": len(records),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_cache_hits_tokens": total_cache_hits,
            "total_cost_usd": round(total_cost_usd, 4),
            "cost_by_agent": {k: round(v, 4) for k, v in by_agent.items()},
            "cost_by_model": {k: round(v, 4) for k, v in by_model.items()}
        }

    def check_budget_alert(
        self,
        organization_id: str,
        monthly_budget_usd: float = 100.0
    ) -> Dict[str, Any]:
        """Evaluate organization spend against monthly budget thresholds (Warning at 80%, Exceeded at 100%)."""
        summary = self.get_organization_cost_summary(organization_id)
        current_spend = summary["total_cost_usd"]

        percentage_used = (current_spend / monthly_budget_usd) * 100.0 if monthly_budget_usd > 0 else 0.0
        alert_status = "NORMAL"

        if percentage_used >= 100.0:
            alert_status = "CRITICAL_BUDGET_EXCEEDED"
        elif percentage_used >= 80.0:
            alert_status = "WARNING_BUDGET_NEAR_LIMIT"

        return {
            "organization_id": organization_id,
            "monthly_budget_usd": monthly_budget_usd,
            "current_spend_usd": current_spend,
            "percentage_used": round(percentage_used, 2),
            "alert_status": alert_status,
            "requires_action": alert_status != "NORMAL"
        }


# Singleton Instance Manager
_cost_monitoring_service_instance: Optional[CostMonitoringService] = None

def get_cost_monitoring_service() -> CostMonitoringService:
    """Get global CostMonitoringService singleton instance."""
    global _cost_monitoring_service_instance
    if _cost_monitoring_service_instance is None:
        _cost_monitoring_service_instance = CostMonitoringService()
    return _cost_monitoring_service_instance
