from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Callable, Optional, Tuple

class TaskCategory(str, Enum):
    DAG_GENERATION = "dag_generation"
    CONTEXT_ANALYSIS = "context_analysis"
    OUTPUT_REFLECTION = "output_reflection"
    ENTITY_EMBEDDINGS = "entity_embeddings"
    SEARCH_RERANKING = "search_reranking"

class BudgetTier(str, Enum):
    HIGH_BUDGET = "high_budget"
    STANDARD = "standard"
    LOW_BUDGET = "low_budget"

@dataclass
class ModelRouteConfig:
    primary_model: str
    fallback_model: str
    input_rate_per_1k: float  # USD per 1000 input tokens
    output_rate_per_1k: float # USD per 1000 output tokens
    max_context_window: int   # max token window limit
    selection_reason: str

ROUTING_MATRIX: Dict[TaskCategory, ModelRouteConfig] = {
    TaskCategory.DAG_GENERATION: ModelRouteConfig(
        primary_model="claude-3-5-sonnet",
        fallback_model="gpt-4o",
        input_rate_per_1k=0.003,
        output_rate_per_1k=0.015,
        max_context_window=200000,
        selection_reason="Requires complex HTN reasoning and strict JSON schema output."
    ),
    TaskCategory.CONTEXT_ANALYSIS: ModelRouteConfig(
        primary_model="gemini-1-5-flash",
        fallback_model="llama-3-8b",
        input_rate_per_1k=0.00035,
        output_rate_per_1k=0.00105,
        max_context_window=1000000,
        selection_reason="Requires massive context window at minimal token cost."
    ),
    TaskCategory.OUTPUT_REFLECTION: ModelRouteConfig(
        primary_model="claude-3-5-sonnet",
        fallback_model="gpt-4o",
        input_rate_per_1k=0.003,
        output_rate_per_1k=0.015,
        max_context_window=200000,
        selection_reason="Requires high accuracy self-correction and validation."
    ),
    TaskCategory.ENTITY_EMBEDDINGS: ModelRouteConfig(
        primary_model="text-embedding-3-small",
        fallback_model="cohere-embed",
        input_rate_per_1k=0.00002,
        output_rate_per_1k=0.0,
        max_context_window=8191,
        selection_reason="Cost-effective vector embedding generation."
    ),
    TaskCategory.SEARCH_RERANKING: ModelRouteConfig(
        primary_model="cohere-rerank",
        fallback_model="local-cross-encoder",
        input_rate_per_1k=0.0001,
        output_rate_per_1k=0.0001,
        max_context_window=4096,
        selection_reason="Optimized relevance scoring for hybrid search."
    )
}

class ModelRouter:
    """Dynamic Cost-Optimized LLM Model Router & Failover Engine."""

    def select_model(
        self,
        task_category: str,
        budget_tier: str = "standard",
        token_length: int = 1000
    ) -> Dict[str, Any]:
        """
        Dynamically select the target primary model, fallback model, and estimated cost
        based on task category, token payload size, and budget tier constraints.
        """
        try:
            category_enum = TaskCategory(task_category.lower())
        except ValueError:
            category_enum = TaskCategory.CONTEXT_ANALYSIS

        try:
            budget_enum = BudgetTier(budget_tier.lower())
        except ValueError:
            budget_enum = BudgetTier.STANDARD

        config = ROUTING_MATRIX[category_enum]
        primary = config.primary_model
        fallback = config.fallback_model

        # Adjust for low-budget constraints
        if budget_enum == BudgetTier.LOW_BUDGET and category_enum == TaskCategory.DAG_GENERATION:
            primary = "gemini-1-5-flash"
            fallback = "llama-3-8b"

        # Calculate estimated cost for 1k input / 0.5k output
        est_cost = (token_length / 1000.0) * config.input_rate_per_1k + (500 / 1000.0) * config.output_rate_per_1k

        return {
            "task_category": category_enum.value,
            "budget_tier": budget_enum.value,
            "primary_model": primary,
            "fallback_model": fallback,
            "estimated_cost_usd": round(est_cost, 6),
            "max_context_window": config.max_context_window,
            "selection_reason": config.selection_reason
        }

    async def execute_with_failover(
        self,
        task_category: str,
        invoke_fn: Callable[[str], Any],
        budget_tier: str = "standard"
    ) -> Dict[str, Any]:
        """
        Execute task against primary model; if primary model fails (e.g. rate limit, 5xx server error,
        or circuit breaker open), automatically failover to fallback model and record trace.
        """
        route = self.select_model(task_category, budget_tier)
        primary_model = route["primary_model"]
        fallback_model = route["fallback_model"]

        try:
            # Attempt primary model call
            res = await invoke_fn(primary_model) if callable(invoke_fn) else invoke_fn
            return {
                "status": "SUCCESS",
                "model_used": primary_model,
                "failover_occurred": False,
                "result": res
            }
        except Exception as primary_err:
            # Failover to secondary model
            try:
                res_fallback = await invoke_fn(fallback_model) if callable(invoke_fn) else invoke_fn
                return {
                    "status": "SUCCESS_FALLBACK",
                    "model_used": fallback_model,
                    "failover_occurred": True,
                    "primary_error": str(primary_err),
                    "result": res_fallback
                }
            except Exception as fallback_err:
                return {
                    "status": "FAILED",
                    "model_used": None,
                    "failover_occurred": True,
                    "primary_error": str(primary_err),
                    "fallback_error": str(fallback_err)
                }


# Singleton Instance Manager
_model_router_instance: Optional[ModelRouter] = None

def get_model_router() -> ModelRouter:
    """Get global ModelRouter singleton instance."""
    global _model_router_instance
    if _model_router_instance is None:
        _model_router_instance = ModelRouter()
    return _model_router_instance
