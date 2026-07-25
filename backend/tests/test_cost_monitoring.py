import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.cost_monitoring import (
    get_cost_monitoring_service,
    CostMonitoringService,
    TokenUsageRecord
)

async def test_cost_monitoring_flow():
    print("Initializing AI Cost Monitoring & Budget Alert Engine validation tests...")
    service = get_cost_monitoring_service()
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    # 1. Test Cost Formula Calculation
    print("\nTest 1: Testing LLM token cost USD formula calculation...")
    # claude-3-5-sonnet: 4500 prompt tokens ($0.0135), 850 completion tokens ($0.01275), 1200 cache hit tokens ($0.0018 savings)
    cost = service.calculate_call_cost(
        model="claude-3-5-sonnet",
        prompt_tokens=4500,
        completion_tokens=850,
        cache_hit_tokens=1200
    )
    expected = round((4500/1000.0)*0.003 + (850/1000.0)*0.015 - (1200/1000.0)*0.0015, 6)
    assert abs(cost - expected) < 1e-5
    print(f"SUCCESS: Cost calculated accurately (${cost}).")

    # 2. Test Record Usage Logging & Organization Summary
    print("\nTest 2: Logging token usage records and checking organization summary...")
    service.record_usage(org_id, user_id, "PlanningAgent", "claude-3-5-sonnet", 10000, 2000, 1000)
    service.record_usage(org_id, user_id, "CodeAnalystAgent", "gemini-1-5-flash", 50000, 5000, 0)

    summary = service.get_organization_cost_summary(org_id)
    assert summary["total_calls"] == 2
    assert summary["total_prompt_tokens"] == 60000
    assert summary["total_completion_tokens"] == 7000
    assert "PlanningAgent" in summary["cost_by_agent"]
    assert "claude-3-5-sonnet" in summary["cost_by_model"]
    print(f"SUCCESS: Organization token usage aggregated (Total Spend: ${summary['total_cost_usd']}).")

    # 3. Test Budget Threshold Alert Engine
    print("\nTest 3: Testing Budget Threshold Alert Engine (80% warning, 100% breach)...")
    # Low budget of $0.05 will trigger critical breach
    alert_normal = service.check_budget_alert(org_id, monthly_budget_usd=100.0)
    assert alert_normal["alert_status"] == "NORMAL"

    alert_breached = service.check_budget_alert(org_id, monthly_budget_usd=0.01)
    assert alert_breached["alert_status"] == "CRITICAL_BUDGET_EXCEEDED"
    assert alert_breached["requires_action"] is True
    print("SUCCESS: Budget threshold alert statuses verified.")

    # 4. Test REST API Endpoints
    print("\nTest 4: Testing Cost Monitoring HTTP REST API endpoints...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST /api/v1/costs/record
        res_rec = await client.post(
            "/api/v1/costs/record",
            json={
                "organization_id": org_id,
                "user_id": user_id,
                "agent_name": "RiskManagerAgent",
                "model": "gpt-4o",
                "prompt_tokens": 8000,
                "completion_tokens": 1000,
                "cache_hit_tokens": 500
            }
        )
        assert res_rec.status_code == 201

        # GET /api/v1/costs/summary/{org_id}
        res_sum = await client.get(f"/api/v1/costs/summary/{org_id}")
        assert res_sum.status_code == 200
        assert res_sum.json()["total_calls"] == 3

        # GET /api/v1/costs/alerts/{org_id}
        res_alert = await client.get(f"/api/v1/costs/alerts/{org_id}?monthly_budget_usd=1000.0")
        assert res_alert.status_code == 200
        assert res_alert.json()["alert_status"] == "NORMAL"

        print("SUCCESS: Cost Monitoring REST API endpoints verified.")

    print("\nAll AI Cost Monitoring & Budget Alert Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_cost_monitoring_flow())
