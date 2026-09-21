import asyncio
import uuid
from sqlalchemy import select

import app.db.base  # Register models
from app.models.tenant import Organization, Workspace
from app.models.project import Project, Repository, SlackChannelMapping
from app.models.context import ContextChunk, ContextEmbedding
from app.models.event import Event
from app.services.context_ingestion import ContextIngestionService, derive_source_id
from app.services.context import ContextEngineService
from app.services.outbox import OutboxService
from app.events.redis_bus import get_event_bus
from app.db.session import SessionLocal


async def _get_chunks(session, organization_id, source_type, external_id):
    source_id = derive_source_id("github" if source_type.startswith("github") else ("jira" if source_type.startswith("jira") else "slack"), external_id)
    res = await session.execute(
        select(ContextChunk).where(
            ContextChunk.organization_id == organization_id,
            ContextChunk.source_type == source_type,
            ContextChunk.source_id == source_id,
        )
    )
    return list(res.scalars().all())


async def test_context_ingestion_flow():
    print("Initializing Context Ingestion Consumer validation tests...")

    suffix = uuid.uuid4().hex[:6]
    ingestion_service = ContextIngestionService()

    org_a_id = None
    org_b_id = None
    project_a_id = None
    created_chunk_ids = []
    created_event_ids = []

    try:
        async with SessionLocal() as session:
            org_a = Organization(name=f"Ctx Ingest Org A {suffix}", domain=f"ctxingest-a-{suffix}.com")
            org_b = Organization(name=f"Ctx Ingest Org B {suffix}", domain=f"ctxingest-b-{suffix}.com")
            session.add_all([org_a, org_b])
            await session.flush()
            org_a_id, org_b_id = org_a.id, org_b.id

            workspace_a = Workspace(organization_id=org_a_id, name="Ctx Ingest Workspace A")
            session.add(workspace_a)
            await session.flush()

            project_a = Project(
                organization_id=org_a_id, workspace_id=workspace_a.id,
                name="Ctx Ingest Project A", jira_project_key=f"CIP{suffix.upper()}",
            )
            session.add(project_a)
            await session.flush()
            project_a_id = project_a.id

            repo = Repository(
                organization_id=org_a_id, project_id=project_a_id,
                external_repo_id="998877", name=f"acme/ctx-ingest-{suffix}", clone_url="https://github.com/acme/repo.git",
            )
            channel_mapping = SlackChannelMapping(
                organization_id=org_a_id, project_id=project_a_id, slack_channel_id=f"C{suffix.upper()}",
            )
            session.add_all([repo, channel_mapping])
            await session.commit()

        # 1. GitHub issue opened -> real ContextChunk indexed, project resolved via Repository link.
        print("\nTest 1: GitHub 'issues opened' webhook event indexes a real ContextChunk...")
        gh_issue_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "github", "repository": f"acme/ctx-ingest-{suffix}",
                "raw_payload": {
                    "action": "opened",
                    "issue": {"number": 42, "title": "Login button misaligned", "body": "Off by 4px on mobile.", "html_url": "https://github.com/x"},
                    "repository": {"full_name": f"acme/ctx-ingest-{suffix}"},
                },
            },
        }
        await ingestion_service.handle_event("m1", gh_issue_payload)
        async with SessionLocal() as session:
            chunks = await _get_chunks(session, org_a_id, "github_issue", f"acme/ctx-ingest-{suffix}#42")
            assert len(chunks) > 0, "Expected GitHub issue to be indexed as a ContextChunk"
            assert "Login button misaligned" in chunks[0].content
            assert chunks[0].project_id == project_a_id, "Project should auto-resolve via linked Repository"
            created_chunk_ids.extend(c.id for c in chunks)
        print("SUCCESS: GitHub issue indexed with correct content and auto-resolved project_id.")

        # 2. GitHub PR opened -> indexed as github_pr, distinct source_type from issues.
        print("\nTest 2: GitHub 'pull_request opened' webhook event indexes a real ContextChunk...")
        gh_pr_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "github", "repository": f"acme/ctx-ingest-{suffix}",
                "raw_payload": {
                    "action": "opened",
                    "pull_request": {"number": 7, "title": "Fix login alignment", "body": "Resolves #42", "html_url": "https://github.com/y"},
                    "repository": {"full_name": f"acme/ctx-ingest-{suffix}"},
                },
            },
        }
        await ingestion_service.handle_event("m2", gh_pr_payload)
        async with SessionLocal() as session:
            chunks = await _get_chunks(session, org_a_id, "github_pr", f"acme/ctx-ingest-{suffix}#7")
            assert len(chunks) > 0
            assert "Fix login alignment" in chunks[0].content
            created_chunk_ids.extend(c.id for c in chunks)
        print("SUCCESS: GitHub PR indexed separately from issues under github_pr source_type.")

        # 3. GitHub issue "deleted" action is skipped -- not every webhook action should pollute context.
        print("\nTest 3: GitHub 'issues deleted' action is correctly skipped (no chunk created)...")
        gh_deleted_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "github", "repository": f"acme/ctx-ingest-{suffix}",
                "raw_payload": {
                    "action": "deleted",
                    "issue": {"number": 99, "title": "Should not be indexed", "body": "x", "html_url": "https://github.com/z"},
                    "repository": {"full_name": f"acme/ctx-ingest-{suffix}"},
                },
            },
        }
        await ingestion_service.handle_event("m3", gh_deleted_payload)
        async with SessionLocal() as session:
            chunks = await _get_chunks(session, org_a_id, "github_issue", f"acme/ctx-ingest-{suffix}#99")
            assert len(chunks) == 0, "Deleted-action events should not be indexed"
        print("SUCCESS: 'deleted' action correctly produced no ContextChunk.")

        # 4. Jira issue webhook -> indexed, project resolved via Project.jira_project_key (own org).
        print("\nTest 4: Jira issue webhook event indexes a real ContextChunk with project resolution...")
        jira_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"CIP{suffix.upper()}-101", "project_key": f"CIP{suffix.upper()}",
                "raw_payload": {"issue": {"fields": {"summary": "Backend 500 on save", "description": "Stack trace attached.", "status": {"name": "Open"}}}},
            },
        }
        await ingestion_service.handle_event("m4", jira_payload)
        async with SessionLocal() as session:
            chunks = await _get_chunks(session, org_a_id, "jira_issue", f"CIP{suffix.upper()}-101")
            assert len(chunks) > 0
            assert "Backend 500 on save" in chunks[0].content
            assert chunks[0].project_id == project_a_id, "Project should auto-resolve via Project.jira_project_key"
            created_chunk_ids.extend(c.id for c in chunks)
        print("SUCCESS: Jira issue indexed with correct content and auto-resolved project_id.")

        # 5. Tenant isolation: Org B's event referencing Org A's jira_project_key must NOT resolve
        #    to Org A's project (proves resolve_project_for_jira_key is organization-scoped).
        print("\nTest 5: Cross-tenant Jira project-key collision does not leak Org A's project_id...")
        jira_cross_tenant_payload = {
            "organization_id": str(org_b_id), "project_id": None,
            "payload": {
                "provider": "jira", "issue_key": f"CIP{suffix.upper()}-999", "project_key": f"CIP{suffix.upper()}",
                "raw_payload": {"issue": {"fields": {"summary": "Org B issue, same key coincidence", "description": "", "status": {"name": "Open"}}}},
            },
        }
        await ingestion_service.handle_event("m5", jira_cross_tenant_payload)
        async with SessionLocal() as session:
            chunks = await _get_chunks(session, org_b_id, "jira_issue", f"CIP{suffix.upper()}-999")
            assert len(chunks) > 0
            assert chunks[0].project_id is None, "Org B must not resolve to Org A's project via a matching key"
            created_chunk_ids.extend(c.id for c in chunks)
        print("SUCCESS: Cross-tenant jira_project_key collision did not leak Org A's project_id.")

        # 6. Slack message event -> indexed, project resolved via existing SlackChannelMapping.
        print("\nTest 6: Slack 'message' event indexes a real ContextChunk with channel-mapped project...")
        slack_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "slack", "channel": f"C{suffix.upper()}", "user": "U123",
                "raw_payload": {"event": {"type": "message", "channel": f"C{suffix.upper()}", "user": "U123", "text": "Deploy is stuck on staging", "ts": "1699999999.000100"}},
            },
        }
        await ingestion_service.handle_event("m6", slack_payload)
        async with SessionLocal() as session:
            chunks = await _get_chunks(session, org_a_id, "slack_message", f"C{suffix.upper()}:1699999999.000100")
            assert len(chunks) > 0
            assert "Deploy is stuck on staging" in chunks[0].content
            assert chunks[0].project_id == project_a_id
            created_chunk_ids.extend(c.id for c in chunks)
        print("SUCCESS: Slack message indexed with correct content and channel-mapped project_id.")

        # 7. Idempotency: redelivering the same GitHub issue event replaces, not duplicates, its chunks.
        print("\nTest 7: Redelivering the same event replaces prior chunks instead of duplicating...")
        gh_issue_edited_payload = {
            "organization_id": str(org_a_id), "project_id": None,
            "payload": {
                "provider": "github", "repository": f"acme/ctx-ingest-{suffix}",
                "raw_payload": {
                    "action": "edited",
                    "issue": {"number": 42, "title": "Login button misaligned", "body": "Off by 4px on mobile AND desktop.", "html_url": "https://github.com/x"},
                    "repository": {"full_name": f"acme/ctx-ingest-{suffix}"},
                },
            },
        }
        await ingestion_service.handle_event("m7", gh_issue_edited_payload)
        async with SessionLocal() as session:
            chunks = await _get_chunks(session, org_a_id, "github_issue", f"acme/ctx-ingest-{suffix}#42")
            assert len(chunks) == 1, f"Expected exactly 1 chunk after re-index (replace, not accumulate), got {len(chunks)}"
            assert "desktop" in chunks[0].content
            created_chunk_ids.extend(c.id for c in chunks)
        print("SUCCESS: Re-indexing the same source replaced its chunk instead of duplicating.")

        # 8. Full end-to-end wiring: real Event row -> OutboxService -> Event Bus publish ->
        #    subscribed consumer -> real ContextChunk, with no direct handler call.
        print("\nTest 8: End-to-end Outbox -> Event Bus -> Context Ingestion consumer wiring...")
        event_bus = get_event_bus()
        await event_bus.connect()
        await event_bus.subscribe("github_stream", "context_engine", "context_engine_test_consumer", ingestion_service.handle_event)

        e2e_event_id = None
        async with SessionLocal() as session:
            db_event = Event(
                organization_id=org_a_id,
                routing_key="github:issues:opened",
                payload={
                    "provider": "github", "repository": f"acme/ctx-ingest-{suffix}",
                    "raw_payload": {
                        "action": "opened",
                        "issue": {"number": 55, "title": "E2E pipeline issue", "body": "Full wiring proof.", "html_url": "https://github.com/e2e"},
                        "repository": {"full_name": f"acme/ctx-ingest-{suffix}"},
                    },
                },
                processed=False,
            )
            session.add(db_event)
            await session.commit()
            e2e_event_id = db_event.id
            created_event_ids.append(e2e_event_id)

            outbox = OutboxService(session)
            count = await outbox.process_outbox()
            assert count >= 1

        chunks = []
        for _ in range(20):
            await asyncio.sleep(0.25)
            async with SessionLocal() as session:
                chunks = await _get_chunks(session, org_a_id, "github_issue", f"acme/ctx-ingest-{suffix}#55")
            if chunks:
                break
        async with SessionLocal() as session:
            assert len(chunks) > 0, "End-to-end pipeline (Outbox -> Event Bus -> Consumer) did not index the event"
            assert "E2E pipeline issue" in chunks[0].content
            created_chunk_ids.extend(c.id for c in chunks)
        print("SUCCESS: Real Outbox event flowed through the Event Bus into a real indexed ContextChunk.")

    finally:
        print("\nCleaning up test database entries...")
        async with SessionLocal() as session:
            for cid in created_chunk_ids:
                res = await session.execute(select(ContextEmbedding).where(ContextEmbedding.chunk_id == cid))
                for emb in res.scalars().all():
                    await session.delete(emb)
                res = await session.execute(select(ContextChunk).where(ContextChunk.id == cid))
                chk = res.scalar_one_or_none()
                if chk:
                    await session.delete(chk)
            for eid in created_event_ids:
                res = await session.execute(select(Event).where(Event.id == eid))
                ev = res.scalar_one_or_none()
                if ev:
                    await session.delete(ev)
            await session.flush()
            if project_a_id:
                res = await session.execute(select(Repository).where(Repository.project_id == project_a_id))
                for r in res.scalars().all():
                    await session.delete(r)
                res = await session.execute(select(SlackChannelMapping).where(SlackChannelMapping.project_id == project_a_id))
                for m in res.scalars().all():
                    await session.delete(m)
                await session.flush()
                res = await session.execute(select(Project).where(Project.id == project_a_id))
                proj = res.scalar_one_or_none()
                if proj:
                    await session.delete(proj)
                await session.flush()
            for org_id in (org_a_id, org_b_id):
                if not org_id:
                    continue
                res = await session.execute(select(Workspace).where(Workspace.organization_id == org_id))
                for w in res.scalars().all():
                    await session.delete(w)
                await session.flush()
                res = await session.execute(select(Organization).where(Organization.id == org_id))
                org = res.scalar_one_or_none()
                if org:
                    await session.delete(org)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Context Ingestion Consumer tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_context_ingestion_flow())
