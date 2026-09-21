import asyncio
import uuid
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

import app.db.base  # Register models
from app.models.tenant import Organization, Workspace
from app.models.project import Project, Repository
from app.services.context_ingestion import ContextIngestionService
from app.db.session import SessionLocal


async def test_realtime_activity_push_flow():
    print("Initializing Real-Time Activity Push (Phase 66) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    ingestion_service = ContextIngestionService()
    repo_name = f"acme/rt-push-{suffix}"

    org_a_id = None
    project_a_id = None
    project_no_repo_id = None

    try:
        async with SessionLocal() as session:
            org_a = Organization(name=f"RT Push Org A {suffix}", domain=f"rtpush-a-{suffix}.com")
            session.add(org_a)
            await session.flush()
            org_a_id = org_a.id

            workspace_a = Workspace(organization_id=org_a_id, name="RT Push Workspace A")
            session.add(workspace_a)
            await session.flush()

            project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="RT Push Project A")
            project_no_repo = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="RT Push Project (unlinked)")
            session.add_all([project_a, project_no_repo])
            await session.flush()
            project_a_id, project_no_repo_id = project_a.id, project_no_repo.id

            repo = Repository(organization_id=org_a_id, project_id=project_a_id, external_repo_id="1", name=repo_name, clone_url=f"https://github.com/{repo_name}.git")
            session.add(repo)
            await session.commit()
        print(f"Test org/project created. Org A={org_a_id} repo={repo_name} linked to Project A={project_a_id}")

        # 1. A real GitHub issue event, once indexed, broadcasts exactly one real-time
        #    activity_update to the event's real organization, with the correct payload.
        print("\nTest 1: Verifying a real indexed event broadcasts a real-time activity_update...")
        fake_manager = AsyncMock()
        gh_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "github", "repository": repo_name,
                "raw_payload": {
                    "action": "opened",
                    "issue": {"number": 7, "title": "Crash on save", "body": "Stack trace attached.", "html_url": "https://github.com/x"},
                    "repository": {"full_name": repo_name},
                },
            },
        }
        with patch("app.realtime.connection_manager.get_connection_manager", return_value=fake_manager):
            await ingestion_service.handle_event("rt1", gh_payload)

        assert fake_manager.broadcast_to_organization.await_count == 1, "Expected exactly one broadcast call"
        broadcast_payload, broadcast_org = fake_manager.broadcast_to_organization.await_args.args
        assert broadcast_org == org_a_id
        assert broadcast_payload["event"] == "activity_update"
        assert broadcast_payload["payload"]["source_type"] == "github_issue"
        assert broadcast_payload["payload"]["provider"] == "github"
        assert broadcast_payload["payload"]["title"] == "Crash on save"
        assert broadcast_payload["payload"]["project_id"] == str(project_a_id)
        assert broadcast_payload["payload"]["url"] == "https://github.com/x"
        print("SUCCESS: Real event correctly broadcast a real-time activity_update with the right payload.")

        # 2. An event that resolves no real project produces no broadcast -- an unscoped
        #    event isn't useful against project-scoped dashboard UI.
        print("\nTest 2: Verifying an event with no resolvable project produces no broadcast...")
        fake_manager_2 = AsyncMock()
        unlinked_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "github", "repository": "acme/totally-unlinked-rt",
                "raw_payload": {
                    "action": "opened",
                    "issue": {"number": 1, "title": "Should not broadcast", "body": "x", "html_url": "https://github.com/z"},
                    "repository": {"full_name": "acme/totally-unlinked-rt"},
                },
            },
        }
        with patch("app.realtime.connection_manager.get_connection_manager", return_value=fake_manager_2):
            await ingestion_service.handle_event("rt2", unlinked_payload)
        assert fake_manager_2.broadcast_to_organization.await_count == 0, "Expected no broadcast for an unscoped event"
        print("SUCCESS: Unscoped event correctly produced no broadcast.")

        # 3. A real Jira issue event also broadcasts correctly (title = summary).
        print("\nTest 3: Verifying a real Jira event broadcasts with the summary as its title...")
        async with SessionLocal() as session:
            res_p = await session.execute(select(Project).where(Project.id == project_a_id))
            proj = res_p.scalar_one()
            proj.jira_project_key = f"RTP{suffix.upper()}"
            await session.commit()

        fake_manager_3 = AsyncMock()
        jira_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"RTP{suffix.upper()}-1", "project_key": f"RTP{suffix.upper()}",
                "raw_payload": {"issue": {"fields": {"summary": "Backend 500 on save", "description": "", "status": {"name": "Open"}}}},
            },
        }
        with patch("app.realtime.connection_manager.get_connection_manager", return_value=fake_manager_3):
            await ingestion_service.handle_event("rt3", jira_payload)
        assert fake_manager_3.broadcast_to_organization.await_count == 1
        payload3, org3 = fake_manager_3.broadcast_to_organization.await_args.args
        assert org3 == org_a_id
        assert payload3["payload"]["title"] == "Backend 500 on save"
        assert payload3["payload"]["source_type"] == "jira_issue"
        print("SUCCESS: Real Jira event correctly broadcast with its summary as the title.")

    finally:
        print("\nCleaning up test database entries...")
        async with SessionLocal() as session:
            if project_a_id:
                res = await session.execute(select(Repository).where(Repository.project_id == project_a_id))
                for r in res.scalars().all():
                    await session.delete(r)
                await session.flush()
            for pid in (project_a_id, project_no_repo_id):
                if not pid:
                    continue
                res = await session.execute(select(Project).where(Project.id == pid))
                p = res.scalar_one_or_none()
                if p:
                    await session.delete(p)
            await session.flush()
            if org_a_id:
                res = await session.execute(select(Workspace).where(Workspace.organization_id == org_a_id))
                for w in res.scalars().all():
                    await session.delete(w)
                await session.flush()
                org_row = await session.get(Organization, org_a_id)
                if org_row:
                    await session.delete(org_row)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Real-Time Activity Push tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_realtime_activity_push_flow())
