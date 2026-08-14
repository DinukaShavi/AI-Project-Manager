import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.models.tenant import Organization, User
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

async def test_frontend_api_contract_flow():
    print("Initializing Frontend-to-Backend API Contract Integration validation tests...")
    org_id = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # 1. Test Observability API route contract
        res_obs = await client.get("/api/v1/observability/metrics")
        assert res_obs.status_code == 200
        assert "telemetry_metrics" in res_obs.json()
        print("SUCCESS: Frontend API contract verified for Observability metrics.")

        # 2. Test Security API route contract
        res_sec = await client.post("/api/v1/security/scan-prompt", json={"input_text": "safe prompt"})
        assert res_sec.status_code == 200
        assert "is_injection" in res_sec.json()
        print("SUCCESS: Frontend API contract verified for Security prompt scanner.")

        # 3. Test Rate Limiter API route contract
        res_rl = await client.post("/api/v1/rate-limit/check", json={"dimension": "user", "identifier": "fe-user-1", "tokens_needed": 1.0})
        assert res_rl.status_code == 200
        assert "remaining" in res_rl.json()
        print("SUCCESS: Frontend API contract verified for Rate Limiter token bucket.")

        # 4. Test Model Router API route contract
        res_mod = await client.get("/api/v1/models/matrix")
        assert res_mod.status_code == 200
        assert "routing_matrix" in res_mod.json()
        print("SUCCESS: Frontend API contract verified for Model Router matrix.")

        # 5. Test AI Cost Monitoring API route contract -- authenticated, organization_id
        # derived from the caller (backend/app/api/v1/costs.py's IDOR fix).
        async with SessionLocal() as session:
            org = Organization(name=f"Contract Test Org {uuid.uuid4().hex[:6]}", domain=f"contract-{uuid.uuid4().hex[:6]}.com")
            session.add(org)
            await session.flush()
            org_id = str(org.id)
            await session.commit()
        cost_headers = await create_authenticated_headers(client, org_id)
        res_cost = await client.get(f"/api/v1/costs/summary/{org_id}", headers=cost_headers)
        assert res_cost.status_code == 200
        assert "total_cost_usd" in res_cost.json()
        print("SUCCESS: Frontend API contract verified for Cost Monitoring summary.")

        # 6. Test Knowledge Graph Evolution API route contract
        res_graph = await client.get("/api/v1/graph-evolution/traverse/node-1")
        assert res_graph.status_code == 200
        assert "active_outbound_edges" in res_graph.json()
        print("SUCCESS: Frontend API contract verified for Knowledge Graph traversal.")

    if org_id:
        async with SessionLocal() as session:
            user_res = await session.execute(select(User).where(User.organization_id == uuid.UUID(org_id)))
            for u in user_res.scalars().all():
                await session.delete(u)
            await session.commit()
            org_res = await session.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
            db_org = org_res.scalar_one_or_none()
            if db_org:
                await session.delete(db_org)
            await session.commit()

    print("\nAll Frontend-to-Backend API Contract Integration tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_frontend_api_contract_flow())
