import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.models.tenant import Organization, Workspace
from app.models.project import Project, Repository
from app.models.graph import ContextSnapshot
from app.models.context import ContextChunk, ContextEmbedding
from app.services.context_ingestion import ContextIngestionService
from app.services.context_snapshot import ContextSnapshotService
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_context_snapshot_population_flow():
    print("Initializing ContextSnapshot Population (Phase 68) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    ingestion_service = ContextIngestionService()
    repo_name = f"acme/snap-{suffix}"

    org_a_id = None
    org_b_id = None
    project_a_id = None
    project_no_activity_id = None
    created_snapshot_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Snapshot Org A {suffix}", domain=f"snap-a-{suffix}.com")
                org_b = Organization(name=f"Snapshot Org B {suffix}", domain=f"snap-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Snapshot Workspace A")
                session.add(workspace_a)
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Snapshot Project A")
                project_no_activity = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Snapshot Project (no activity)")
                session.add_all([project_a, project_no_activity])
                await session.flush()
                project_a_id, project_no_activity_id = project_a.id, project_no_activity.id

                repo = Repository(organization_id=org_a_id, project_id=project_a_id, external_repo_id="1", name=repo_name, clone_url=f"https://github.com/{repo_name}.git")
                session.add(repo)
                await session.commit()
            print(f"Test org/projects created. Org A={org_a_id} repo={repo_name} linked to Project A={project_a_id}")

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            # 1. A project with no real activity has no snapshot -- never fabricated.
            print("\nTest 1: Verifying a project with no real activity has no snapshot...")
            res = await client.get(f"/api/v1/context/projects/{project_no_activity_id}/snapshot", headers=headers_a)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: No-activity project correctly has no snapshot.")

            # 2. A real GitHub event, once indexed, auto-generates a real ContextSnapshot with
            #    a templated summary built from real data.
            print("\nTest 2: Verifying a real ingested event auto-generates a real ContextSnapshot...")
            gh_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": repo_name,
                    "raw_payload": {
                        "action": "opened",
                        "issue": {"number": 7, "title": "Crash on save", "body": "Stack trace.", "html_url": "https://github.com/x"},
                        "repository": {"full_name": repo_name},
                    },
                },
            }
            await ingestion_service.handle_event("snap1", gh_payload)

            res = await client.get(f"/api/v1/context/projects/{project_a_id}/snapshot", headers=headers_a)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            body = res.json()
            assert "Crash on save" in body["state_payload"]["summary"]
            assert body["state_payload"]["recent_activity"][0]["source_type"] == "github_issue"
            first_snapshot_id = body["id"]
            async with SessionLocal() as session:
                snap = await session.get(ContextSnapshot, uuid.UUID(first_snapshot_id))
                assert snap is not None
                assert len(snap.summary_embedding) == 1536
                created_snapshot_ids.append(snap.id)
            print("SUCCESS: Real event auto-generated a real ContextSnapshot with a real embedded summary.")

            # 3. A second real event within the 15-minute throttle window does not create
            #    another snapshot -- same snapshot id.
            print("\nTest 3: Verifying the throttle window prevents a second snapshot...")
            gh_payload_2 = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": repo_name,
                    "raw_payload": {
                        "action": "opened",
                        "issue": {"number": 8, "title": "Another issue", "body": "x", "html_url": "https://github.com/y"},
                        "repository": {"full_name": repo_name},
                    },
                },
            }
            await ingestion_service.handle_event("snap2", gh_payload_2)
            res = await client.get(f"/api/v1/context/projects/{project_a_id}/snapshot", headers=headers_a)
            assert res.status_code == 200, res.text
            assert res.json()["id"] == first_snapshot_id, "Expected the throttle to prevent a new snapshot"
            print("SUCCESS: Throttle window correctly prevented a redundant snapshot.")

            # 4. POST /snapshot bypasses the throttle for an explicit on-demand request.
            print("\nTest 4: Verifying the on-demand endpoint bypasses the throttle...")
            res = await client.post(f"/api/v1/context/projects/{project_a_id}/snapshot", headers=headers_a)
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            second_snapshot_id = res.json()["id"]
            assert second_snapshot_id != first_snapshot_id
            assert "Another issue" in res.json()["state_payload"]["summary"]
            async with SessionLocal() as session:
                created_snapshot_ids.append(uuid.UUID(second_snapshot_id))
            print("SUCCESS: On-demand endpoint correctly bypassed the throttle and produced a fresh snapshot.")

            # 5. Manually backdating the latest snapshot past the throttle window allows a
            #    real event to auto-regenerate again.
            print("\nTest 5: Verifying a stale snapshot is regenerated by a new real event...")
            async with SessionLocal() as session:
                # Backdate every existing snapshot for this project, not just the most recent
                # one -- get_latest_snapshot orders by snapshot_timestamp, so an earlier row
                # left un-backdated would still be picked as "latest" and mask the staleness.
                res = await session.execute(select(ContextSnapshot).where(ContextSnapshot.project_id == project_a_id))
                for snap in res.scalars().all():
                    snap.snapshot_timestamp = datetime.now(timezone.utc) - timedelta(minutes=20)
                await session.commit()

            gh_payload_3 = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": repo_name,
                    "raw_payload": {
                        "action": "opened",
                        "issue": {"number": 9, "title": "Third issue after staleness", "body": "x", "html_url": "https://github.com/z"},
                        "repository": {"full_name": repo_name},
                    },
                },
            }
            await ingestion_service.handle_event("snap3", gh_payload_3)
            res = await client.get(f"/api/v1/context/projects/{project_a_id}/snapshot", headers=headers_a)
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["id"] != second_snapshot_id
            assert "Third issue after staleness" in body["state_payload"]["summary"]
            async with SessionLocal() as session:
                created_snapshot_ids.append(uuid.UUID(body["id"]))
            print("SUCCESS: Stale snapshot correctly regenerated by a new real event.")

            # 6. Cross-tenant isolation.
            print("\nTest 6: Verifying cross-tenant isolation...")
            res = await client.get(f"/api/v1/context/projects/{project_a_id}/snapshot", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant access correctly rejected (404).")

        finally:
            print("\nCleaning up test database entries...")
            async with SessionLocal() as session:
                for sid in set(created_snapshot_ids):
                    res = await session.execute(select(ContextSnapshot).where(ContextSnapshot.id == sid))
                    row = res.scalar_one_or_none()
                    if row:
                        await session.delete(row)
                await session.flush()
                # Also sweep any snapshot rows this test's own events may have produced beyond
                # the ones explicitly tracked above (e.g. from the auto-trigger paths).
                if project_a_id:
                    res = await session.execute(select(ContextSnapshot).where(ContextSnapshot.project_id == project_a_id))
                    for row in res.scalars().all():
                        await session.delete(row)
                    res = await session.execute(select(ContextEmbedding).join(ContextChunk).where(ContextChunk.project_id == project_a_id))
                    for row in res.scalars().all():
                        await session.delete(row)
                    await session.flush()
                    res = await session.execute(select(ContextChunk).where(ContextChunk.project_id == project_a_id))
                    for row in res.scalars().all():
                        await session.delete(row)
                    res = await session.execute(select(Repository).where(Repository.project_id == project_a_id))
                    for r in res.scalars().all():
                        await session.delete(r)
                await session.flush()
                for pid in (project_a_id, project_no_activity_id):
                    if not pid:
                        continue
                    res = await session.execute(select(Project).where(Project.id == pid))
                    p = res.scalar_one_or_none()
                    if p:
                        await session.delete(p)
                await session.flush()
                for oid in (org_a_id, org_b_id):
                    if not oid:
                        continue
                    from app.models.tenant import User
                    res = await session.execute(select(Workspace).where(Workspace.organization_id == oid))
                    for w in res.scalars().all():
                        await session.delete(w)
                    res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in res.scalars().all():
                        await session.delete(u)
                    await session.flush()
                    org_row = await session.get(Organization, oid)
                    if org_row:
                        await session.delete(org_row)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll ContextSnapshot Population tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_context_snapshot_population_flow())
