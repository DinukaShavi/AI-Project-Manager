from typing import Dict, List, Any, Optional
import uuid

class RecommendationEngine:
    """Graph-based and Monte Carlo risk scoring recommendation engine."""

    def generate_recommendations(
        self,
        graph_state: Optional[Any] = None,
        monte_carlo_results: Optional[Dict[str, Any]] = None,
        tasks_data: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Generate prioritized risk mitigation recommendations."""
        recommendations = []

        # 1. Monte Carlo Delay Warning
        if monte_carlo_results:
            prob_on_time = monte_carlo_results.get("completion_prob_on_time", 1.0)
            if prob_on_time < 0.60:
                p95 = monte_carlo_results.get("p95_days", 14)
                recommendations.append({
                    "id": str(uuid.uuid4()),
                    "title": "High Probability of Sprint Schedule Overrun",
                    "description": f"Monte Carlo 1,000-run simulation indicates only {int(prob_on_time * 100)}% on-time completion probability. P95 forecast is {p95} days.",
                    "recommendation_type": "sprint_delay_warning",
                    "score": 0.90,
                    "action_suggested": "Descope low-priority backlog items or reassign unassigned story points."
                })

        # 2. Graph Bottleneck Clusters
        if graph_state and hasattr(graph_state, "find_bottleneck_clusters"):
            bottlenecks = graph_state.find_bottleneck_clusters()
            for b in bottlenecks:
                recommendations.append({
                    "id": str(uuid.uuid4()),
                    "title": f"Dependency Bottleneck Detected on {b.get('type', 'entity')}",
                    "description": f"Entity '{b.get('urn')}' blocks {b.get('blocking_count')} items and is blocked by {b.get('blocked_by_count')} items.",
                    "recommendation_type": "graph_bottleneck",
                    "score": 0.85,
                    "action_suggested": "Prioritize unblocking parent pull request / dependency node."
                })

        # 3. Developer Overload Warning
        if tasks_data:
            assigned_counts: Dict[str, int] = {}
            for t in tasks_data:
                assignee = t.get("assignee") or t.get("assignee_id") or "unassigned"
                assigned_counts[assignee] = assigned_counts.get(assignee, 0) + 1

            for assignee, count in assigned_counts.items():
                if assignee != "unassigned" and count >= 5:
                    recommendations.append({
                        "id": str(uuid.uuid4()),
                        "title": f"Developer Overload Risk for '{assignee}'",
                        "description": f"Developer '{assignee}' is assigned {count} active tasks exceeding recommended capacity.",
                        "recommendation_type": "developer_overload",
                        "score": 0.75,
                        "action_suggested": f"Reallocate tasks from '{assignee}' to available team members."
                    })

        # Fallback Default Recommendation
        if not recommendations:
            recommendations.append({
                "id": str(uuid.uuid4()),
                "title": "Sprint Pace Healthy",
                "description": "No critical bottlenecks or high-risk schedule overruns detected in current sprint graph.",
                "recommendation_type": "health_check",
                "score": 0.20,
                "action_suggested": "Maintain current development trajectory."
            })

        return sorted(recommendations, key=lambda x: x["score"], reverse=True)
