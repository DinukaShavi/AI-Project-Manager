import asyncio
import uuid
from sqlalchemy import select

import app.db.base  # Register models
from app.core.security import get_password_hash
from app.models.tenant import Organization, Workspace, User, Role
from app.models.project import Project, ProjectTask
from app.models.integration import Integration
from app.models.external_identity import ExternalIdentity
from app.services.context_ingestion import ContextIngestionService
from app.services.external_identity import ExternalIdentityService
from app.db.session import SessionLocal


async def _get_task(session, organization_id, project_id, issue_key):
    res = await session.execute(
        select(ProjectTask).where(
            ProjectTask.organization_id == organization_id,
            ProjectTask.project_id == project_id,
            ProjectTask.jira_issue_key == issue_key,
        )
    )
    return res.scalar_one_or_none()


async def test_jira_task_sync_flow():
    print("Initializing Real Jira Issue -> ProjectTask Sync (Phase 76) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    ingestion_service = ContextIngestionService()
    project_key = f"JTS{suffix.upper()}"

    org_a_id = None
    org_b_id = None
    project_a_id = None
    project_b_id = None
    resolved_user_id = None

    try:
        async with SessionLocal() as session:
            org_a = Organization(name=f"Jira Task Sync Org A {suffix}", domain=f"jts-a-{suffix}.com")
            org_b = Organization(name=f"Jira Task Sync Org B {suffix}", domain=f"jts-b-{suffix}.com")
            session.add_all([org_a, org_b])
            await session.flush()
            org_a_id, org_b_id = org_a.id, org_b.id

            workspace_a = Workspace(organization_id=org_a_id, name="JTS Workspace A")
            workspace_b = Workspace(organization_id=org_b_id, name="JTS Workspace B")
            session.add_all([workspace_a, workspace_b])
            await session.flush()

            project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="JTS Project A", jira_project_key=project_key)
            project_b = Project(organization_id=org_b_id, workspace_id=workspace_b.id, name="JTS Project B", jira_project_key=project_key)
            session.add_all([project_a, project_b])
            await session.flush()
            project_a_id, project_b_id = project_a.id, project_b.id

            viewer_role = (await session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()
            resolved_user = User(
                organization_id=org_a_id, email=f"jts-dev-{suffix}@example.com", full_name="JTS Resolved Dev",
                hashed_password=get_password_hash("TestPass123!"),
            )
            resolved_user.roles.append(viewer_role)
            session.add(resolved_user)
            await session.flush()
            resolved_user_id = resolved_user.id

            gh_integration = Integration(organization_id=org_a_id, provider="jira", is_active=True)
            session.add(gh_integration)
            await session.flush()
            await ExternalIdentityService(session).link_identity(
                organization_id=org_a_id, user_id=resolved_user_id, integration_id=gh_integration.id,
                provider="jira", external_account_id="jts-acc-1", external_display_name="JTS Resolved Dev",
            )
            await session.commit()
        print(f"Test orgs/projects created. Org A={org_a_id} Project A={project_a_id} (jira_project_key={project_key})")

        # 1. A real webhook event for a new issue creates a real ProjectTask with mirrored
        #    title/status/assignee.
        print("\nTest 1: Verifying a real webhook event creates a real ProjectTask...")
        webhook_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"{project_key}-1", "project_key": project_key,
                "raw_payload": {"issue": {"fields": {
                    "summary": "Fix login race condition", "description": "Users report intermittent failures.",
                    "status": {"name": "To Do", "statusCategory": {"key": "new"}},
                    "assignee": {"accountId": "jts-acc-1"},
                }}},
            },
        }
        await ingestion_service.handle_event("jts1", webhook_payload)
        async with SessionLocal() as session:
            task = await _get_task(session, org_a_id, project_a_id, f"{project_key}-1")
            assert task is not None, "Expected a real ProjectTask to be created from the real Jira issue"
            assert task.title == "Fix login race condition"
            assert task.status == "todo"
            assert task.assignee_id == resolved_user_id
        print("SUCCESS: Real ProjectTask created with correct title/status/resolved assignee.")

        # 2. A second event for the SAME issue key updates the existing task in place.
        print("\nTest 2: Verifying a second event updates the existing task instead of duplicating it...")
        update_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"{project_key}-1", "project_key": project_key,
                "raw_payload": {"issue": {"fields": {
                    "summary": "Fix login race condition (updated)", "description": "Root caused.",
                    "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
                    "assignee": {"accountId": "jts-acc-1"},
                }}},
            },
        }
        await ingestion_service.handle_event("jts2", update_payload)
        async with SessionLocal() as session:
            res = await session.execute(
                select(ProjectTask).where(
                    ProjectTask.organization_id == org_a_id, ProjectTask.project_id == project_a_id,
                    ProjectTask.jira_issue_key == f"{project_key}-1",
                )
            )
            tasks = list(res.scalars().all())
            assert len(tasks) == 1, f"Expected exactly 1 task after update (upsert, not duplicate), got {len(tasks)}"
            assert tasks[0].title == "Fix login race condition (updated)"
            assert tasks[0].status == "in_progress"
        print("SUCCESS: Existing task correctly updated in place, not duplicated.")

        # 3. An update with no resolvable status category leaves the existing status untouched.
        print("\nTest 3: Verifying an unresolvable status category does not downgrade the task's status...")
        no_category_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"{project_key}-1", "project_key": project_key,
                "raw_payload": {"issue": {"fields": {
                    "summary": "Fix login race condition (updated)", "description": "",
                    "status": {"name": "Some Custom Status"},  # no statusCategory
                    "assignee": {"accountId": "jts-acc-1"},
                }}},
            },
        }
        await ingestion_service.handle_event("jts3", no_category_payload)
        async with SessionLocal() as session:
            task = await _get_task(session, org_a_id, project_a_id, f"{project_key}-1")
            assert task.status == "in_progress", "Status must not be downgraded/guessed when statusCategory is unavailable"
        print("SUCCESS: Task status correctly preserved when statusCategory is unresolvable.")

        # 4. An issue with no assignee clears assignee_id back to None.
        print("\nTest 4: Verifying an unassigned issue clears the task's assignee...")
        unassigned_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"{project_key}-1", "project_key": project_key,
                "raw_payload": {"issue": {"fields": {
                    "summary": "Fix login race condition (updated)", "description": "",
                    "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
                    "assignee": None,
                }}},
            },
        }
        await ingestion_service.handle_event("jts4", unassigned_payload)
        async with SessionLocal() as session:
            task = await _get_task(session, org_a_id, project_a_id, f"{project_key}-1")
            assert task.assignee_id is None, "Removing the Jira assignee must clear the task's assignee (Jira is source of truth)"
        print("SUCCESS: Task assignee correctly cleared when the Jira issue became unassigned.")

        # 5. The real backup-sync payload shape (status_category/assignee_account_id passed
        #    through, Phase 76's fix) also produces a correctly-synced task.
        print("\nTest 5: Verifying the real backup-sync payload shape also syncs a task correctly...")
        backup_sync_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"{project_key}-2", "project_key": project_key,
                "summary": "Backend 500 on save", "status": "Done",
                "status_category": "done", "assignee_account_id": "jts-acc-1",
                "source": "backup_sync",
            },
        }
        await ingestion_service.handle_event("jts5", backup_sync_payload)
        async with SessionLocal() as session:
            task = await _get_task(session, org_a_id, project_a_id, f"{project_key}-2")
            assert task is not None, "Expected the backup-sync payload to create a real ProjectTask too"
            assert task.title == "Backend 500 on save"
            assert task.status == "done"
            assert task.assignee_id == resolved_user_id
        print("SUCCESS: Real backup-sync payload correctly synced a task (status_category/assignee pass-through works).")

        # 6. Cross-tenant: the same issue_key in a different org must not resolve to Org A's
        #    task -- Org B's own project (coincidentally sharing the same jira_project_key)
        #    gets its own separate task, Org A's is untouched.
        print("\nTest 6: Verifying cross-tenant isolation on the same issue key...")
        cross_tenant_payload = {
            "organization_id": str(org_b_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"{project_key}-1", "project_key": project_key,
                "raw_payload": {"issue": {"fields": {
                    "summary": "Org B's own issue, coincidentally same key", "description": "",
                    "status": {"name": "To Do", "statusCategory": {"key": "new"}},
                    "assignee": None,
                }}},
            },
        }
        await ingestion_service.handle_event("jts6", cross_tenant_payload)
        async with SessionLocal() as session:
            org_a_task = await _get_task(session, org_a_id, project_a_id, f"{project_key}-1")
            assert org_a_task.title == "Fix login race condition (updated)", "Org B's event must not have touched Org A's task"
            org_b_task = await _get_task(session, org_b_id, project_b_id, f"{project_key}-1")
            assert org_b_task is not None
            assert org_b_task.title == "Org B's own issue, coincidentally same key"
        print("SUCCESS: Cross-tenant isolation correctly held -- each org got its own separate task.")

    finally:
        print("\nCleaning up test database entries...")
        async with SessionLocal() as session:
            for org_id in (org_a_id, org_b_id):
                if not org_id:
                    continue
                res = await session.execute(select(ExternalIdentity).where(ExternalIdentity.organization_id == org_id))
                for ident in res.scalars().all():
                    await session.delete(ident)
                res = await session.execute(select(Integration).where(Integration.organization_id == org_id))
                for i in res.scalars().all():
                    await session.delete(i)
            await session.flush()
            for pid in (project_a_id, project_b_id):
                if not pid:
                    continue
                res = await session.execute(select(ProjectTask).where(ProjectTask.project_id == pid))
                for t in res.scalars().all():
                    await session.delete(t)
            await session.flush()
            for pid in (project_a_id, project_b_id):
                if not pid:
                    continue
                res = await session.execute(select(Project).where(Project.id == pid))
                p = res.scalar_one_or_none()
                if p:
                    await session.delete(p)
            await session.flush()
            for org_id in (org_a_id, org_b_id):
                if not org_id:
                    continue
                res = await session.execute(select(Workspace).where(Workspace.organization_id == org_id))
                for w in res.scalars().all():
                    await session.delete(w)
                res = await session.execute(select(User).where(User.organization_id == org_id))
                for u in res.scalars().all():
                    await session.delete(u)
            await session.flush()
            for org_id in (org_a_id, org_b_id):
                if not org_id:
                    continue
                org_row = await session.get(Organization, org_id)
                if org_row:
                    await session.delete(org_row)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Real Jira Issue -> ProjectTask Sync tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_jira_task_sync_flow())
