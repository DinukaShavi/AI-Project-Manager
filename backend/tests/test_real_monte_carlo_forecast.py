import asyncio
import uuid
import httpx
from unittest.mock import patch
from sqlalchemy import select

import app.db.base  # Register models
from app.core.security import encrypt_token
from app.models.tenant import Organization, Workspace
from app.models.project import Project, ProjectTask
from app.models.integration import Integration, OAuthToken
from app.services.intelligence_engine import ProjectIntelligenceEngine
from app.db.session import SessionLocal

_real_get = httpx.AsyncClient.get
CLOUD_ID = "cloud-site-id-mc80"
PROJECT_KEY = "MC80"


async def _fake_jira_get(self, url, **kwargs):
    url_s = str(url)
    base = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}"
    if url_s == f"{base}/rest/api/3/field":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json=[{"id": "customfield_10099", "name": "Story Points"}])
    if url_s == f"{base}/rest/agile/1.0/board":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"values": [{"id": 901, "name": f"{PROJECT_KEY} board"}]})
    if url_s == f"{base}/rest/agile/1.0/board/901/sprint":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"values": [
            {"id": 1001, "name": "Sprint 1", "state": "closed", "startDate": "2026-07-01T00:00:00Z", "endDate": "2026-07-15T00:00:00Z"},
        ]})
    if url_s == f"{base}/rest/agile/1.0/sprint/1001/issue":
        req = httpx.Request("GET", url_s)
        return httpx.Response(200, request=req, json={"issues": [
            {"fields": {"customfield_10099": 5, "status": {"statusCategory": {"key": "done"}}}},
            {"fields": {"customfield_10099": 3, "status": {"statusCategory": {"key": "done"}}}},
        ]})
    return await _real_get(self, url, **kwargs)


async def test_real_monte_carlo_forecast_flow():
    print("Initializing Real Monte Carlo Forecast Inputs (Phase 80) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_real_id = None
    org_empty_id = None
    project_real_id = None
    project_empty_id = None
    created_task_ids = []

    try:
        async with SessionLocal() as session:
            org_real = Organization(name=f"MC Real Org {suffix}", domain=f"mc-real-{suffix}.com")
            org_empty = Organization(name=f"MC Empty Org {suffix}", domain=f"mc-empty-{suffix}.com")
            session.add_all([org_real, org_empty])
            await session.flush()
            org_real_id, org_empty_id = org_real.id, org_empty.id

            ws_real = Workspace(organization_id=org_real_id, name="MC Real Workspace")
            ws_empty = Workspace(organization_id=org_empty_id, name="MC Empty Workspace")
            session.add_all([ws_real, ws_empty])
            await session.flush()

            project_real = Project(organization_id=org_real_id, workspace_id=ws_real.id, name="MC Real Project", jira_project_key=PROJECT_KEY)
            project_empty = Project(organization_id=org_empty_id, workspace_id=ws_empty.id, name="MC Empty Project")
            session.add_all([project_real, project_empty])
            await session.flush()
            project_real_id, project_empty_id = project_real.id, project_empty.id

            integration = Integration(organization_id=org_real_id, provider="jira", is_active=True, external_workspace_id=CLOUD_ID)
            session.add(integration)
            await session.flush()
            token = OAuthToken(organization_id=org_real_id, integration_id=integration.id, encrypted_access_token=encrypt_token("fake-jira-token"), scopes=["read:jira-work"])
            session.add(token)

            task_open_1 = ProjectTask(organization_id=org_real_id, project_id=project_real_id, title="Open task 1", status="todo", story_points=5)
            task_open_2 = ProjectTask(organization_id=org_real_id, project_id=project_real_id, title="Open task 2", status="in_progress", story_points=3)
            task_done = ProjectTask(organization_id=org_real_id, project_id=project_real_id, title="Done task", status="done", story_points=10)
            session.add_all([task_open_1, task_open_2, task_done])
            await session.commit()
            created_task_ids = [task_open_1.id, task_open_2.id, task_done.id]
        print(f"Test orgs/projects created. Org Real={org_real_id} (real Jira velocity + real remaining points) Org Empty={org_empty_id} (no real data)")

        # 1. Real project data (real Jira velocity, real remaining ProjectTask points), no
        #    explicit caller overrides: both inputs resolve to real values.
        print("\nTest 1: Verifying the forecast is grounded in real Jira velocity and real remaining points...")
        with patch.object(httpx.AsyncClient, "get", new=_fake_jira_get):
            async with SessionLocal() as session:
                engine = ProjectIntelligenceEngine(session)
                result = await engine.process_goal(
                    goal="Audit sprint delivery health",
                    organization_id=str(org_real_id),
                    project_id=str(project_real_id),
                    user_role="Developer",
                )
        assert result["forecast_data_source"] == {"velocities": "real", "remaining_points": "real"}, result["forecast_data_source"]
        assert result["monte_carlo_predictive"]["num_simulations"] > 0
        print("SUCCESS: Forecast correctly used real Jira velocity and real remaining ProjectTask points.")

        # 2. No real data available (no Jira connection, no tasks), no explicit overrides:
        #    falls back to the exact original hardcoded defaults.
        print("\nTest 2: Verifying the forecast falls back to honest defaults when no real data exists...")
        async with SessionLocal() as session:
            engine = ProjectIntelligenceEngine(session)
            result_empty = await engine.process_goal(
                goal="Audit sprint delivery health",
                organization_id=str(org_empty_id),
                project_id=str(project_empty_id),
                user_role="Developer",
            )
        assert result_empty["forecast_data_source"] == {"velocities": "default", "remaining_points": "default"}, result_empty["forecast_data_source"]
        print("SUCCESS: Forecast correctly fell back to honest default source labels with no real data.")

        # 3. Explicit caller-supplied overrides are honored as-is, never overwritten by real
        #    data even when real data exists for this same project.
        print("\nTest 3: Verifying explicit caller overrides are honored and correctly labeled...")
        with patch.object(httpx.AsyncClient, "get", new=_fake_jira_get):
            async with SessionLocal() as session:
                engine = ProjectIntelligenceEngine(session)
                result_override = await engine.process_goal(
                    goal="Audit sprint delivery health",
                    organization_id=str(org_real_id),
                    project_id=str(project_real_id),
                    user_role="Developer",
                    historical_velocities=[1.0, 2.0, 3.0],
                    remaining_points=42.0,
                )
        assert result_override["forecast_data_source"] == {"velocities": "caller", "remaining_points": "caller"}
        print("SUCCESS: Explicit caller overrides correctly honored and labeled, not overwritten by real data.")

        # 4. The no-db unit-test path is unaffected -- falls straight to honest defaults.
        print("\nTest 4: Verifying the no-db path is unaffected...")
        engine_no_db = ProjectIntelligenceEngine()
        result_no_db = await engine_no_db.process_goal(
            goal="Audit sprint delivery health",
            organization_id=str(org_real_id),
        )
        assert result_no_db["forecast_data_source"] == {"velocities": "default", "remaining_points": "default"}
        print("SUCCESS: No-db path correctly preserved, falls straight to honest defaults.")

    finally:
        print("\nCleaning up test database entries...")
        async with SessionLocal() as session:
            for tid in created_task_ids:
                res = await session.execute(select(ProjectTask).where(ProjectTask.id == tid))
                t = res.scalar_one_or_none()
                if t:
                    await session.delete(t)
            await session.flush()
            for org_id in (org_real_id, org_empty_id):
                if not org_id:
                    continue
                res = await session.execute(select(OAuthToken).where(OAuthToken.organization_id == org_id))
                for row in res.scalars().all():
                    await session.delete(row)
                res = await session.execute(select(Integration).where(Integration.organization_id == org_id))
                for i in res.scalars().all():
                    await session.delete(i)
                await session.flush()
            for pid in (project_real_id, project_empty_id):
                if not pid:
                    continue
                res = await session.execute(select(Project).where(Project.id == pid))
                p = res.scalar_one_or_none()
                if p:
                    await session.delete(p)
            await session.flush()
            for org_id in (org_real_id, org_empty_id):
                if not org_id:
                    continue
                res = await session.execute(select(Workspace).where(Workspace.organization_id == org_id))
                for w in res.scalars().all():
                    await session.delete(w)
                await session.flush()
                org_row = await session.get(Organization, org_id)
                if org_row:
                    await session.delete(org_row)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Real Monte Carlo Forecast Inputs tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_real_monte_carlo_forecast_flow())
