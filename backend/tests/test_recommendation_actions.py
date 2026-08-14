import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.models.audit import AuditLog
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def _trigger_recommendation_generation(client: AsyncClient, headers: dict, project_id) -> dict:
    """Drive the real, existing recommendation-generation flow (same helper as
    test_recommendations.py) to persist real Recommendation rows via the production
    pipeline rather than fabricating DB rows directly."""
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


async def test_recommendation_actions_flow():
    print("Initializing Recommendation Actions API validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Rec Action Org A {suffix}", domain=f"recact-a-{suffix}.com")
                org_b = Organization(name=f"Rec Action Org B {suffix}", domain=f"recact-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Rec Action Workspace A")
                session.add(workspace_a)
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Rec Action Project A")
                session.add(project_a)
                await session.commit()
                project_a_id = project_a.id

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs/project created. Org A={org_a_id} Project A={project_a_id} Org B={org_b_id}")

            await _trigger_recommendation_generation(client, headers_a, project_a_id)
            async with SessionLocal() as session:
                res_db = await session.execute(select(Recommendation).where(Recommendation.organization_id == org_a_id))
                persisted = res_db.scalars().all()
                assert len(persisted) >= 1
            rec_id = persisted[0].id
            print(f"SUCCESS: Seeded {len(persisted)} real recommendation(s) via the production pipeline. Using id={rec_id}.")

            # 1. Dismiss transitions status to 'dismissed' and logs an audit feedback entry
            # (ui_ux_design.md section 13: "Dismiss recommendation (logs feedback)").
            print("\nTest 1: Verifying 'dismiss' action transitions status and logs feedback...")
            res = await client.post(
                f"/api/v1/recommendations/{rec_id}/action",
                json={"action": "dismiss"},
                headers=headers_a,
            )
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            body = res.json()
            assert body["id"] == str(rec_id)
            assert body["status"] == "dismissed"
            print("SUCCESS: Recommendation status transitioned to 'dismissed'.")

            async with SessionLocal() as session:
                rec = await session.get(Recommendation, rec_id)
                assert rec.status == "dismissed"

                audit_res = await session.execute(
                    select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action == "recommendation:dismiss")
                )
                audit_row = audit_res.scalars().first()
                assert audit_row is not None, "Expected an audit log entry for the dismiss action"
                assert audit_row.details["recommendation_id"] == str(rec_id)
            print("SUCCESS: Status persisted and audit feedback log entry created.")

            # 2. The filtered list endpoint reflects the new status.
            print("\nTest 2: Verifying the dismissed recommendation now appears under ?status=dismissed...")
            res = await client.get("/api/v1/recommendations?status=dismissed", headers=headers_a)
            assert res.status_code == 200
            assert any(r["id"] == str(rec_id) for r in res.json()["recommendations"])
            print("SUCCESS: GET /recommendations?status=dismissed reflects the transition.")

            # 3. Accept transitions status to 'accepted'.
            print("\nTest 3: Verifying 'accept' action transitions status to 'accepted'...")
            res = await client.post(
                f"/api/v1/recommendations/{rec_id}/action",
                json={"action": "accept"},
                headers=headers_a,
            )
            assert res.status_code == 200, res.text
            assert res.json()["status"] == "accepted"
            async with SessionLocal() as session:
                rec = await session.get(Recommendation, rec_id)
                assert rec.status == "accepted"
            print("SUCCESS: Recommendation status transitioned to 'accepted'.")

            # 4. An unsupported action value is rejected with a clean 400, not a crash.
            print("\nTest 4: Verifying an unsupported action value returns 400...")
            res = await client.post(
                f"/api/v1/recommendations/{rec_id}/action",
                json={"action": "delete"},
                headers=headers_a,
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Unsupported action correctly rejected with 400.")

            # 5. THE CRITICAL CHECK: Org B cannot act on Org A's recommendation.
            print("\nTest 5: Verifying cross-tenant action is rejected...")
            res = await client.post(
                f"/api/v1/recommendations/{rec_id}/action",
                json={"action": "dismiss"},
                headers=headers_b,
            )
            assert res.status_code == 404, f"Expected 404 for cross-tenant action, got {res.status_code}: {res.text}"
            async with SessionLocal() as session:
                rec = await session.get(Recommendation, rec_id)
                assert rec.status == "accepted", "Org B's rejected attempt must not have changed Org A's recommendation status"
            print("SUCCESS: Org B correctly rejected (404); Org A's recommendation status unchanged.")

            # 6. A nonexistent recommendation_id must 404, not 500.
            print("\nTest 6: Verifying a nonexistent recommendation_id returns 404...")
            res = await client.post(
                f"/api/v1/recommendations/{uuid.uuid4()}/action",
                json={"action": "dismiss"},
                headers=headers_a,
            )
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Nonexistent recommendation_id correctly returns 404.")

            # 7. Unauthenticated requests are rejected.
            print("\nTest 7: Verifying an unauthenticated request is rejected...")
            res = await client.post(f"/api/v1/recommendations/{rec_id}/action", json={"action": "dismiss"})
            assert res.status_code in (401, 403), f"Expected 401/403, got {res.status_code}: {res.text}"
            print(f"SUCCESS: Unauthenticated request correctly rejected ({res.status_code}).")

        finally:
            print("\nCleaning up recommendation actions test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    audit_res = await session.execute(select(AuditLog).where(AuditLog.organization_id == oid))
                    for a in audit_res.scalars().all():
                        await session.delete(a)
                    await session.commit()

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

    print("\nAll Recommendation Actions API tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_recommendation_actions_flow())
