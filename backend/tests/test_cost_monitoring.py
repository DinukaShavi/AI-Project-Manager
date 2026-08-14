import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.models.tenant import Organization, User
from app.db.session import SessionLocal
from app.services.cost_monitoring import (
    get_cost_monitoring_service,
    CostMonitoringService,
    TokenUsageRecord
)
from tests._auth_helpers import create_authenticated_headers

async def test_cost_monitoring_flow():
    print("Initializing AI Cost Monitoring & Budget Alert Engine validation tests...")
    service = get_cost_monitoring_service()

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None

    async with SessionLocal() as session:
        org_a = Organization(name=f"Cost Test Org A {suffix}", domain=f"cost-a-{suffix}.com")
        org_b = Organization(name=f"Cost Test Org B {suffix}", domain=f"cost-b-{suffix}.com")
        session.add_all([org_a, org_b])
        await session.commit()
        org_a_id, org_b_id = str(org_a.id), str(org_b.id)

    org_id = org_a_id
    user_id = str(uuid.uuid4())

    try:
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
        alert_normal = service.check_budget_alert(org_id, monthly_budget_usd=100.0)
        assert alert_normal["alert_status"] == "NORMAL"

        alert_breached = service.check_budget_alert(org_id, monthly_budget_usd=0.01)
        assert alert_breached["alert_status"] == "CRITICAL_BUDGET_EXCEEDED"
        assert alert_breached["requires_action"] is True
        print("SUCCESS: Budget threshold alert statuses verified.")

        # 4. Test REST API Endpoints -- now require authentication; organization_id is
        # derived from the authenticated caller, never client-supplied (matches the
        # tenant-isolation convention established throughout this session).
        print("\nTest 4: Testing Cost Monitoring HTTP REST API endpoints (authenticated)...")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            # Unauthenticated requests are rejected outright.
            res = await client.get(f"/api/v1/costs/summary/{org_id}")
            assert res.status_code == 401, f"Expected 401 for an unauthenticated request, got {res.status_code}"

            # POST /api/v1/costs/record -- no organization_id/user_id in the body anymore;
            # both are derived from the authenticated caller.
            res_rec = await client.post(
                "/api/v1/costs/record",
                json={
                    "agent_name": "RiskManagerAgent",
                    "model": "gpt-4o",
                    "prompt_tokens": 8000,
                    "completion_tokens": 1000,
                    "cache_hit_tokens": 500
                },
                headers=headers_a,
            )
            assert res_rec.status_code == 201, res_rec.text
            assert res_rec.json()["record"]["organization_id"] == org_a_id

            # GET /api/v1/costs/summary/{org_id} -- own org succeeds.
            res_sum = await client.get(f"/api/v1/costs/summary/{org_id}", headers=headers_a)
            assert res_sum.status_code == 200
            assert res_sum.json()["total_calls"] == 3

            # GET /api/v1/costs/alerts/{org_id} -- own org succeeds.
            res_alert = await client.get(f"/api/v1/costs/alerts/{org_id}?monthly_budget_usd=1000.0", headers=headers_a)
            assert res_alert.status_code == 200
            assert res_alert.json()["alert_status"] == "NORMAL"

            print("SUCCESS: Cost Monitoring REST API endpoints verified for the owning organization.")

            # 5. Cross-tenant isolation: Org B cannot read Org A's cost summary/alerts by
            # supplying Org A's organization_id in the path, and cannot write usage records
            # attributed to Org A either.
            print("\nTest 5: Verifying Org B cannot access or attribute usage to Org A's cost data...")
            res = await client.get(f"/api/v1/costs/summary/{org_id}", headers=headers_b)
            assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
            assert "another organization" in res.json()["detail"].lower()

            res = await client.get(f"/api/v1/costs/alerts/{org_id}", headers=headers_b)
            assert res.status_code == 403

            res = await client.post(
                "/api/v1/costs/record",
                json={"agent_name": "SpoofAgent", "model": "gpt-4o", "prompt_tokens": 1, "completion_tokens": 1},
                headers=headers_b,
            )
            assert res.status_code == 201
            assert res.json()["record"]["organization_id"] == org_b_id, "Org B's usage record must be attributed to Org B, never Org A"

            # Org A's summary must be unaffected by Org B's write.
            res_sum_after = await client.get(f"/api/v1/costs/summary/{org_id}", headers=headers_a)
            assert res_sum_after.json()["total_calls"] == 3, "Org B's write must not appear in Org A's summary"
            print("SUCCESS: Org B cannot read Org A's cost data and cannot attribute usage to Org A.")

    finally:
        print("\nCleaning up cost monitoring test database entries...")
        async with SessionLocal() as session:
            for oid in [org_a_id, org_b_id]:
                user_res = await session.execute(select(User).where(User.organization_id == uuid.UUID(oid)))
                for u in user_res.scalars().all():
                    await session.delete(u)
                await session.commit()
                org_res = await session.execute(select(Organization).where(Organization.id == uuid.UUID(oid)))
                db_org = org_res.scalar_one_or_none()
                if db_org:
                    await session.delete(db_org)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll AI Cost Monitoring & Budget Alert Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_cost_monitoring_flow())
