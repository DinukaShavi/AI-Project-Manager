import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def _trigger_recommendation_generation(client: AsyncClient, headers: dict, project_id) -> dict:
    """Drive the real, existing recommendation-generation flow (ProjectIntelligenceEngine.
    process_goal via POST /planning/intelligence) with parameters chosen to deterministically
    trigger the Monte Carlo 'sprint_delay_warning' recommendation (score 0.90): a single very
    low historical velocity against a very large remaining_points backlog drives
    completion_prob_on_time well below the 0.60 threshold."""
    res = await client.post(
        "/api/v1/planning/intelligence",
        json={
            "goal": "Audit sprint delivery health",
            "project_id": str(project_id),
            "historical_velocities": [1.0],
            "remaining_points": 500.0,
        },
        headers=headers,
    )
    assert res.status_code == 200, f"Intelligence pipeline failed: {res.text}"
    return res.json()


async def test_recommendations_flow():
    print("Initializing Recommendations API validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Recs Tenant Org A {suffix}", domain=f"recs-a-{suffix}.com")
                org_b = Organization(name=f"Recs Tenant Org B {suffix}", domain=f"recs-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Recs Workspace A")
                session.add(workspace_a)
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Recs Project A")
                session.add(project_a)
                await session.commit()
                project_a_id = project_a.id

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs/project created. Org A={org_a_id} Project A={project_a_id} Org B={org_b_id}")

            # 1. Empty result before anything has been generated.
            print("\nTest 1: Verifying an empty recommendations list before generation...")
            res = await client.get("/api/v1/recommendations", headers=headers_a)
            assert res.status_code == 200, res.text
            assert res.json()["recommendations"] == []
            print("SUCCESS: Empty recommendations list returned correctly.")

            # 2. Drive the real, existing generation flow to persist recommendations under
            # Org A's project (no fabricated DB rows -- generated via the production pipeline).
            print("\nTest 2: Generating real recommendations via POST /planning/intelligence...")
            intel_result = await _trigger_recommendation_generation(client, headers_a, project_a_id)
            assert len(intel_result["recommendations"]) > 0
            print(f"SUCCESS: Intelligence pipeline generated {len(intel_result['recommendations'])} recommendation(s).")

            async with SessionLocal() as session:
                res_db = await session.execute(select(Recommendation).where(Recommendation.organization_id == org_a_id))
                persisted = res_db.scalars().all()
                assert len(persisted) > 0, "Recommendations must be persisted under Org A's organization_id"
                assert all(r.project_id == project_a_id for r in persisted)
                assert any(r.recommendation_type == "sprint_delay_warning" for r in persisted)
            print(f"SUCCESS: {len(persisted)} recommendation(s) persisted under Org A with correct organization_id/project_id.")

            # 3. Org A can retrieve its own recommendations via the documented endpoint.
            print("\nTest 3: Verifying Org A can retrieve its own recommendations...")
            res = await client.get("/api/v1/recommendations", headers=headers_a)
            assert res.status_code == 200, res.text
            body = res.json()
            assert len(body["recommendations"]) == len(persisted)
            first = body["recommendations"][0]
            assert set(first.keys()) == {"id", "title", "description", "score", "created_at"}
            assert any(r["title"] == "High Probability of Sprint Schedule Overrun" for r in body["recommendations"])
            print("SUCCESS: Org A retrieved its own recommendations with the documented response schema.")

            # 4. Org B cannot see Org A's recommendations, even though no organization_id is
            # client-suppliable on this endpoint at all -- tenant identity comes only from
            # the authenticated user.
            print("\nTest 4: Verifying Org B cannot see Org A's recommendations...")
            res = await client.get("/api/v1/recommendations", headers=headers_b)
            assert res.status_code == 200, res.text
            b_body = res.json()
            assert b_body["recommendations"] == [], f"Org B must see zero recommendations, got: {b_body}"
            raw_text = res.text
            assert "Sprint Schedule Overrun" not in raw_text
            assert str(project_a_id) not in raw_text
            print("SUCCESS: Org B sees zero recommendations; no Org A content leaked.")

            # 5. status filter (per api_contract.md 12.A: ?status=active&type=overload).
            print("\nTest 5: Verifying the status filter works as documented...")
            res = await client.get("/api/v1/recommendations?status=active", headers=headers_a)
            assert res.status_code == 200
            assert len(res.json()["recommendations"]) == len(persisted)

            res = await client.get("/api/v1/recommendations?status=dismissed", headers=headers_a)
            assert res.status_code == 200
            assert res.json()["recommendations"] == [], "No recommendations are dismissed yet"
            print("SUCCESS: status filter correctly narrows results.")

            # 6. type filter.
            print("\nTest 6: Verifying the type filter works as documented...")
            res = await client.get("/api/v1/recommendations?type=sprint_delay_warning", headers=headers_a)
            assert res.status_code == 200
            type_results = res.json()["recommendations"]
            assert len(type_results) >= 1
            assert all(r["title"] == "High Probability of Sprint Schedule Overrun" for r in type_results)

            res = await client.get("/api/v1/recommendations?type=nonexistent_type_xyz", headers=headers_a)
            assert res.status_code == 200
            assert res.json()["recommendations"] == []
            print("SUCCESS: type filter correctly narrows results; unknown type returns empty, not an error.")

            # 7. Combined status+type filter.
            print("\nTest 7: Verifying combined status+type filters work together...")
            res = await client.get("/api/v1/recommendations?status=active&type=sprint_delay_warning", headers=headers_a)
            assert res.status_code == 200
            assert len(res.json()["recommendations"]) >= 1
            print("SUCCESS: Combined status+type filters work correctly.")

            # 8. Deduplication: re-triggering the same generation flow against unchanged
            # conditions must not create duplicate active rows for the same project/type/title.
            print("\nTest 8: Verifying repeated generation does not create duplicate active recommendations...")
            await _trigger_recommendation_generation(client, headers_a, project_a_id)
            async with SessionLocal() as session:
                res_db = await session.execute(select(Recommendation).where(Recommendation.organization_id == org_a_id))
                after_rerun = res_db.scalars().all()
                assert len(after_rerun) == len(persisted), f"Expected no new duplicate rows, had {len(persisted)}, now {len(after_rerun)}"
            print("SUCCESS: Repeated generation did not create duplicate recommendation records.")

        finally:
            print("\nCleaning up recommendations test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    rec_res = await session.execute(select(Recommendation).where(Recommendation.organization_id == oid))
                    for r in rec_res.scalars().all():
                        await session.delete(r)
                    await session.commit()

                    proj_res = await session.execute(select(Project).where(Project.organization_id == oid))
                    for p in proj_res.scalars().all():
                        await session.delete(p)
                    ws_res = await session.execute(select(Workspace).where(Workspace.organization_id == oid))
                    for w in ws_res.scalars().all():
                        await session.delete(w)
                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()

                    org_res = await session.execute(select(Organization).where(Organization.id == oid))
                    db_org = org_res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Recommendations API tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_recommendations_flow())
