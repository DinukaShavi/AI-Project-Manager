import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.analytics.predictor import PredictiveAnalyticsEngine
from app.models.tenant import Organization, Workspace
from app.models.project import Project, ProjectTask
from app.db.session import SessionLocal

async def test_analytics_prediction_flow():
    print("Initializing Predictive Analytics validation tests...")

    # 1. Direct Engine Unit Tests
    print("\nTest 1: Testing PredictiveAnalyticsEngine direct math operations...")
    burndown = PredictiveAnalyticsEngine.calculate_burndown(total_points=40.0, completed_points=20.0, total_days=14, elapsed_days=7)
    assert len(burndown) == 15
    assert burndown[0]["ideal_remaining"] == 40.0
    print("SUCCESS: Burndown trajectory calculated correctly.")

    forecast = PredictiveAnalyticsEngine.predict_completion_date(total_points=40.0, completed_points=20.0, elapsed_days=7, total_sprint_days=14)
    assert forecast["daily_velocity"] == 2.86
    assert forecast["delay_days"] == 0.0
    print("SUCCESS: Completion forecast calculated correctly.")

    risk = PredictiveAnalyticsEngine.predict_risk_score(total_tasks=10, completed_tasks=5, critical_open_tasks=2, unassigned_tasks=1)
    assert risk["risk_level"] in ["medium", "high"]
    print("SUCCESS: Delivery risk assessment score calculated correctly.")

    # 2. HTTP & Database Integration Tests
    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    created_workspace_ids = []
    created_project_ids = []
    created_task_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                print("\nInserting test tenant entries for Analytics API...")
                org = Organization(name=f"Analytics Test Org {suffix}", domain=f"analytics-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id

                ws = Workspace(organization_id=test_org_id, name="Analytics Team")
                session.add(ws)
                await session.flush()
                created_workspace_ids.append(ws.id)

                proj = Project(workspace_id=ws.id, name="Prediction Core Project")
                session.add(proj)
                await session.flush()
                proj_id = proj.id
                created_project_ids.append(proj_id)

                t1 = ProjectTask(project_id=proj_id, title="Feature A", status="done", priority="medium", story_points=8)
                t2 = ProjectTask(project_id=proj_id, title="Feature B", status="in_progress", priority="high", story_points=5)
                t3 = ProjectTask(project_id=proj_id, title="Feature C", status="todo", priority="critical", story_points=13)
                session.add_all([t1, t2, t3])
                await session.flush()
                created_task_ids.extend([t1.id, t2.id, t3.id])

                await session.commit()
                print(f"Test data created. Project ID: {proj_id}")

            # Test GET /api/v1/analytics/burndown
            print("\nTest 2: Requesting GET /api/v1/analytics/burndown...")
            res = await client.get(f"/api/v1/analytics/burndown?project_id={proj_id}")
            assert res.status_code == 200, f"Burndown request failed: {res.text}"
            b_json = res.json()
            assert b_json["total_story_points"] == 26
            assert b_json["completed_story_points"] == 8
            assert len(b_json["burndown_trajectory"]) == 15
            print("SUCCESS: Burndown trajectory fetched via HTTP API.")

            # Test GET /api/v1/analytics/predict-completion
            print("\nTest 3: Requesting GET /api/v1/analytics/predict-completion...")
            res = await client.get(f"/api/v1/analytics/predict-completion?project_id={proj_id}")
            assert res.status_code == 200, f"Predict completion request failed: {res.text}"
            p_json = res.json()
            assert "forecast" in p_json
            assert "risk_assessment" in p_json
            assert p_json["risk_assessment"]["risk_score"] > 0.0
            print(f"SUCCESS: Completion forecast fetched via HTTP API. Risk Score: {p_json['risk_assessment']['risk_score']}")

        finally:
            # Clean up
            print("\nCleaning up analytics test database entries...")
            async with SessionLocal() as session:
                for tid in created_task_ids:
                    res = await session.execute(select(ProjectTask).where(ProjectTask.id == tid))
                    t = res.scalar_one_or_none()
                    if t:
                        await session.delete(t)
                for pid in created_project_ids:
                    res = await session.execute(select(Project).where(Project.id == pid))
                    p = res.scalar_one_or_none()
                    if p:
                        await session.delete(p)
                for wid in created_workspace_ids:
                    res = await session.execute(select(Workspace).where(Workspace.id == wid))
                    w = res.scalar_one_or_none()
                    if w:
                        await session.delete(w)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Predictive Analytics tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_analytics_prediction_flow())
