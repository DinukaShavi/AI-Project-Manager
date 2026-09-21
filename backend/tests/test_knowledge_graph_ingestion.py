import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.core.security import get_password_hash
from app.models.tenant import Organization, Workspace, User, Role
from app.models.project import Project, Repository
from app.models.graph import KnowledgeGraphEdge
from app.models.integration import Integration
from app.models.external_identity import ExternalIdentity
from app.services.context_ingestion import ContextIngestionService
from app.services.external_identity import ExternalIdentityService
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def _get_edges(session, organization_id, project_id):
    res = await session.execute(
        select(KnowledgeGraphEdge).where(
            KnowledgeGraphEdge.organization_id == organization_id,
            KnowledgeGraphEdge.project_id == project_id,
        )
    )
    return list(res.scalars().all())


async def test_knowledge_graph_ingestion_flow():
    print("Initializing Knowledge Graph Edge Auto-Population validation tests...")

    suffix = uuid.uuid4().hex[:6]
    ingestion_service = ContextIngestionService()
    repo_name = f"acme/kg-ingest-{suffix}"

    org_a_id = None
    org_b_id = None
    project_a_id = None
    project_b_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"KG Ingest Org A {suffix}", domain=f"kgingest-a-{suffix}.com")
                org_b = Organization(name=f"KG Ingest Org B {suffix}", domain=f"kgingest-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="KG Ingest Workspace A")
                workspace_b = Workspace(organization_id=org_b_id, name="KG Ingest Workspace B")
                session.add_all([workspace_a, workspace_b])
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="KG Ingest Project A")
                project_b = Project(organization_id=org_b_id, workspace_id=workspace_b.id, name="KG Ingest Project B")
                session.add_all([project_a, project_b])
                await session.flush()
                project_a_id, project_b_id = project_a.id, project_b.id

                repo = Repository(
                    organization_id=org_a_id, project_id=project_a_id,
                    external_repo_id="55221100", name=repo_name, clone_url="https://github.com/acme/repo.git",
                )
                session.add(repo)
                await session.commit()

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)

            # 1. GitHub PR body "Resolves #42" -> a real RESOLVES edge, readable via the
            #    existing GET /context/projects/{id}/graph endpoint with zero changes to it.
            print("\nTest 1: GitHub PR body 'Resolves #42' creates a real RESOLVES edge...")
            pr_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": repo_name,
                    "raw_payload": {
                        "action": "opened",
                        "pull_request": {"number": 7, "title": "Fix crash", "body": "This PR resolves #42 for real.", "html_url": "https://github.com/x"},
                        "repository": {"full_name": repo_name},
                    },
                },
            }
            await ingestion_service.handle_event("k1", pr_payload)
            async with SessionLocal() as session:
                edges = await _get_edges(session, org_a_id, project_a_id)
                resolves = [e for e in edges if e.relation_type == "RESOLVES"]
                assert len(resolves) == 1, f"Expected 1 RESOLVES edge, got {len(resolves)}"
                assert resolves[0].source_urn == f"urn:github:pr:{repo_name}#7"
                assert resolves[0].target_urn == f"urn:github:issue:{repo_name}#42"
            print("SUCCESS: RESOLVES edge correctly derived from PR body.")

            res = await client.get(f"/api/v1/context/projects/{project_a_id}/graph", headers=headers_a)
            assert res.status_code == 200, res.text
            body = res.json()
            assert any(e["relation"] == "RESOLVES" and e["target"] == f"urn:github:issue:{repo_name}#42" for e in body["edges"])
            print("SUCCESS: RESOLVES edge visible via the existing knowledge graph read endpoint.")

            # 2. GitHub PR with an assignee -> a real ASSIGNED_TO edge.
            print("\nTest 2: GitHub PR assignee creates a real ASSIGNED_TO edge...")
            pr_assignee_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": repo_name,
                    "raw_payload": {
                        "action": "assigned",
                        "pull_request": {"number": 9, "title": "Add caching", "body": "", "assignee": {"login": "octo-dev"}, "html_url": "https://github.com/y"},
                        "repository": {"full_name": repo_name},
                    },
                },
            }
            await ingestion_service.handle_event("k2", pr_assignee_payload)
            async with SessionLocal() as session:
                edges = await _get_edges(session, org_a_id, project_a_id)
                assigned = [e for e in edges if e.relation_type == "ASSIGNED_TO" and e.source_urn == f"urn:github:pr:{repo_name}#9"]
                assert len(assigned) == 1
                assert assigned[0].target_urn == "urn:github:user:octo-dev"
            print("SUCCESS: ASSIGNED_TO edge correctly derived from PR assignee.")

            # 3. GitHub issue with an assignee -> a real ASSIGNED_TO edge.
            print("\nTest 3: GitHub issue assignee creates a real ASSIGNED_TO edge...")
            issue_assignee_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": repo_name,
                    "raw_payload": {
                        "action": "assigned",
                        "issue": {"number": 42, "title": "Crash on save", "body": "Stack trace", "assignee": {"login": "octo-dev"}, "html_url": "https://github.com/z"},
                        "repository": {"full_name": repo_name},
                    },
                },
            }
            await ingestion_service.handle_event("k3", issue_assignee_payload)
            async with SessionLocal() as session:
                edges = await _get_edges(session, org_a_id, project_a_id)
                assigned = [e for e in edges if e.relation_type == "ASSIGNED_TO" and e.source_urn == f"urn:github:issue:{repo_name}#42"]
                assert len(assigned) == 1
                assert assigned[0].target_urn == "urn:github:user:octo-dev"
            print("SUCCESS: ASSIGNED_TO edge correctly derived from issue assignee.")

            # 4. Jira issue with an assignee -> a real ASSIGNED_TO edge, project resolved via
            #    Project.jira_project_key.
            print("\nTest 4: Jira issue assignee creates a real ASSIGNED_TO edge...")
            async with SessionLocal() as session:
                res_p = await session.execute(select(Project).where(Project.id == project_a_id))
                proj = res_p.scalar_one()
                proj.jira_project_key = f"KGI{suffix.upper()}"
                await session.commit()

            jira_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "jira", "issue_key": f"KGI{suffix.upper()}-5", "project_key": f"KGI{suffix.upper()}",
                    "raw_payload": {"issue": {"fields": {
                        "summary": "Backend 500 on save", "description": "Trace attached.",
                        "status": {"name": "Open"}, "assignee": {"accountId": "acc-123"},
                    }}},
                },
            }
            await ingestion_service.handle_event("k4", jira_payload)
            async with SessionLocal() as session:
                edges = await _get_edges(session, org_a_id, project_a_id)
                assigned = [e for e in edges if e.relation_type == "ASSIGNED_TO" and e.source_urn == f"urn:jira:issue:KGI{suffix.upper()}-5"]
                assert len(assigned) == 1
                assert assigned[0].target_urn == "urn:jira:user:acc-123"
            print("SUCCESS: ASSIGNED_TO edge correctly derived from Jira issue assignee.")

            # 5. Redelivery: processing the exact same PR event again must not duplicate the edge.
            print("\nTest 5: Redelivering the same event upserts instead of duplicating the edge...")
            await ingestion_service.handle_event("k1-retry", pr_payload)
            async with SessionLocal() as session:
                edges = await _get_edges(session, org_a_id, project_a_id)
                resolves = [e for e in edges if e.relation_type == "RESOLVES"]
                assert len(resolves) == 1, f"Expected exactly 1 RESOLVES edge after redelivery, got {len(resolves)}"
            print("SUCCESS: Redelivered event did not create a duplicate edge.")

            # 6. No project resolvable (unlinked repo) -> no edge written, no crash.
            print("\nTest 6: An event for an unlinked repository writes no edge and does not crash...")
            unlinked_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": "acme/totally-unlinked-repo",
                    "raw_payload": {
                        "action": "opened",
                        "pull_request": {"number": 1, "title": "Orphan PR", "body": "Resolves #1", "html_url": "https://github.com/o"},
                        "repository": {"full_name": "acme/totally-unlinked-repo"},
                    },
                },
            }
            await ingestion_service.handle_event("k5", unlinked_payload)
            async with SessionLocal() as session:
                res = await session.execute(
                    select(KnowledgeGraphEdge).where(KnowledgeGraphEdge.source_urn == "urn:github:pr:acme/totally-unlinked-repo#1")
                )
                assert res.scalar_one_or_none() is None
            print("SUCCESS: Unresolvable-project event wrote no edge and raised no exception.")

            # 7. Cross-tenant isolation: Org B cannot see Org A's edges via its own project graph.
            print("\nTest 7: Org B's knowledge graph does not contain Org A's edges...")
            res = await client.get(f"/api/v1/context/projects/{project_b_id}/graph", headers=headers_b)
            assert res.status_code == 200, res.text
            body = res.json()
            assert len(body["edges"]) == 0
            assert not any(f"#{7}" in n["urn"] for n in body["nodes"])
            print("SUCCESS: Org B's graph correctly shows no edges from Org A's real activity.")

            # 8. A GitHub assignee with a real, active ExternalIdentity resolves to a real
            #    urn:user:id:{id} instead of the external login (Phase 75).
            print("\nTest 8: A GitHub assignee with a linked ExternalIdentity resolves to a real User...")
            async with SessionLocal() as session:
                viewer_role = (await session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()
                resolved_user = User(
                    organization_id=org_a_id, email=f"resolved-gh-{suffix}@example.com", full_name="Resolved GitHub Dev",
                    hashed_password=get_password_hash("TestPass123!"),
                )
                resolved_user.roles.append(viewer_role)
                session.add(resolved_user)
                await session.flush()
                gh_integration = Integration(organization_id=org_a_id, provider="github", is_active=True)
                session.add(gh_integration)
                await session.flush()
                await ExternalIdentityService(session).link_identity(
                    organization_id=org_a_id, user_id=resolved_user.id, integration_id=gh_integration.id,
                    provider="github", external_account_id="999888", external_display_name="resolved-dev",
                )
                await session.commit()
                resolved_user_id = resolved_user.id

            gh_resolved_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": repo_name,
                    "raw_payload": {
                        "action": "assigned",
                        "issue": {"number": 77, "title": "Linked assignee", "body": "x", "assignee": {"login": "resolved-dev", "id": 999888}, "html_url": "https://github.com/w"},
                        "repository": {"full_name": repo_name},
                    },
                },
            }
            await ingestion_service.handle_event("k8", gh_resolved_payload)
            async with SessionLocal() as session:
                edges = await _get_edges(session, org_a_id, project_a_id)
                assigned = [e for e in edges if e.relation_type == "ASSIGNED_TO" and e.source_urn == f"urn:github:issue:{repo_name}#77"]
                assert len(assigned) == 1
                assert assigned[0].target_urn == f"urn:user:id:{resolved_user_id}", f"Expected a real resolved User URN, got {assigned[0].target_urn}"
            print("SUCCESS: GitHub assignee with a linked ExternalIdentity resolved to a real User URN.")

            # 9. A Jira assignee with a real, active ExternalIdentity resolves the same way.
            print("\nTest 9: A Jira assignee with a linked ExternalIdentity resolves to a real User...")
            async with SessionLocal() as session:
                jira_integration = Integration(organization_id=org_a_id, provider="jira", is_active=True)
                session.add(jira_integration)
                await session.flush()
                await ExternalIdentityService(session).link_identity(
                    organization_id=org_a_id, user_id=resolved_user_id, integration_id=jira_integration.id,
                    provider="jira", external_account_id="acc-resolved-1", external_display_name="Resolved Jira Dev",
                )
                await session.commit()

            jira_resolved_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "jira", "issue_key": f"KGI{suffix.upper()}-9", "project_key": f"KGI{suffix.upper()}",
                    "raw_payload": {"issue": {"fields": {
                        "summary": "Linked Jira assignee", "description": "",
                        "status": {"name": "Open"}, "assignee": {"accountId": "acc-resolved-1"},
                    }}},
                },
            }
            await ingestion_service.handle_event("k9", jira_resolved_payload)
            async with SessionLocal() as session:
                edges = await _get_edges(session, org_a_id, project_a_id)
                assigned = [e for e in edges if e.relation_type == "ASSIGNED_TO" and e.source_urn == f"urn:jira:issue:KGI{suffix.upper()}-9"]
                assert len(assigned) == 1
                assert assigned[0].target_urn == f"urn:user:id:{resolved_user_id}", f"Expected a real resolved User URN, got {assigned[0].target_urn}"
            print("SUCCESS: Jira assignee with a linked ExternalIdentity resolved to a real User URN.")

            # 10. Cross-tenant: an ExternalIdentity with the same external_account_id but in a
            #     DIFFERENT organization must not resolve Org A's edge.
            print("\nTest 10: A same-external-id ExternalIdentity in a different org does not resolve...")
            async with SessionLocal() as session:
                viewer_role = (await session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()
                org_b_user = User(
                    organization_id=org_b_id, email=f"org-b-dev-{suffix}@example.com", full_name="Org B Dev",
                    hashed_password=get_password_hash("TestPass123!"),
                )
                org_b_user.roles.append(viewer_role)
                session.add(org_b_user)
                await session.flush()
                org_b_integration = Integration(organization_id=org_b_id, provider="github", is_active=True)
                session.add(org_b_integration)
                await session.flush()
                await ExternalIdentityService(session).link_identity(
                    organization_id=org_b_id, user_id=org_b_user.id, integration_id=org_b_integration.id,
                    provider="github", external_account_id="777666", external_display_name="cross-tenant-dev",
                )
                await session.commit()

            cross_tenant_payload = {
                "organization_id": str(org_a_id), "project_id": None,
                "payload": {
                    "provider": "github", "repository": repo_name,
                    "raw_payload": {
                        "action": "assigned",
                        "issue": {"number": 78, "title": "Cross-tenant assignee", "body": "x", "assignee": {"login": "cross-tenant-dev", "id": 777666}, "html_url": "https://github.com/v"},
                        "repository": {"full_name": repo_name},
                    },
                },
            }
            await ingestion_service.handle_event("k10", cross_tenant_payload)
            async with SessionLocal() as session:
                edges = await _get_edges(session, org_a_id, project_a_id)
                assigned = [e for e in edges if e.relation_type == "ASSIGNED_TO" and e.source_urn == f"urn:github:issue:{repo_name}#78"]
                assert len(assigned) == 1
                assert assigned[0].target_urn == "urn:github:user:cross-tenant-dev", "An identity linked in a different org must not resolve here"
            print("SUCCESS: Cross-tenant ExternalIdentity correctly did not resolve; fell back to the external login URN.")

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
                    res = await session.execute(select(KnowledgeGraphEdge).where(KnowledgeGraphEdge.project_id == pid))
                    for e in res.scalars().all():
                        await session.delete(e)
                    res = await session.execute(select(Repository).where(Repository.project_id == pid))
                    for r in res.scalars().all():
                        await session.delete(r)
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
                    res = await session.execute(select(Organization).where(Organization.id == org_id))
                    org = res.scalar_one_or_none()
                    if org:
                        await session.delete(org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Knowledge Graph Edge Auto-Population tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_knowledge_graph_ingestion_flow())
