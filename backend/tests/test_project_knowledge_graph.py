import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project
from app.models.graph import KnowledgeGraphEdge
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_project_knowledge_graph_flow():
    print("Initializing Project Unified Knowledge Graph validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    project_a_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Graph Tenant Org A {suffix}", domain=f"graph-a-{suffix}.com")
                org_b = Organization(name=f"Graph Tenant Org B {suffix}", domain=f"graph-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id, org_b_id = org_a.id, org_b.id

                workspace_a = Workspace(organization_id=org_a_id, name="Graph Workspace A")
                session.add(workspace_a)
                await session.flush()

                project_a = Project(organization_id=org_a_id, workspace_id=workspace_a.id, name="Graph Project A")
                session.add(project_a)
                await session.flush()
                project_a_id = project_a.id

                edge = KnowledgeGraphEdge(
                    organization_id=org_a_id,
                    project_id=project_a_id,
                    source_urn="urn:jira:issue:SECRET-1",
                    target_urn="urn:github:pr:SECRET-2",
                    relation_type="RESOLVES",
                    weight=0.85,
                )
                session.add(edge)
                await session.commit()

            headers_a = await create_authenticated_headers(client, org_a_id)
            headers_b = await create_authenticated_headers(client, org_b_id)
            print(f"Test orgs/project/edge created. Org A={org_a_id} Project A={project_a_id} Org B={org_b_id}")

            # 1. Org A can retrieve its own project's unified knowledge graph.
            print("\nTest 1: Verifying Org A can retrieve its own project graph...")
            res = await client.get(f"/api/v1/context/projects/{project_a_id}/graph", headers=headers_a)
            assert res.status_code == 200, res.text
            body = res.json()
            node_urns = {n["urn"] for n in body["nodes"]}
            assert "urn:jira:issue:SECRET-1" in node_urns
            assert "urn:github:pr:SECRET-2" in node_urns
            assert len(body["edges"]) == 1
            assert body["edges"][0]["relation"] == "RESOLVES"
            assert body["edges"][0]["source"] == "urn:jira:issue:SECRET-1"
            print("SUCCESS: Org A retrieved its own real project knowledge graph.")

            # 2. Org B cannot retrieve Org A's project graph by supplying Org A's real
            # project_id, and the response leaks no node/edge content.
            print("\nTest 2: Verifying Org B cannot retrieve Org A's project graph...")
            res = await client.get(f"/api/v1/context/projects/{project_a_id}/graph", headers=headers_b)
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            assert res.json()["detail"] == "Project not found in this organization."
            raw_text = res.text
            assert "SECRET-1" not in raw_text
            assert "SECRET-2" not in raw_text
            print("SUCCESS: Org B correctly rejected (404) with no leaked graph data.")

            # 3. A nonexistent project_id returns the identical documented 404 (no
            # existence-leak between cross-tenant and nonexistent cases).
            print("\nTest 3: Verifying a nonexistent project_id returns the same documented 404...")
            res = await client.get(f"/api/v1/context/projects/{uuid.uuid4()}/graph", headers=headers_a)
            assert res.status_code == 404
            assert res.json()["detail"] == "Project not found in this organization."
            print("SUCCESS: Nonexistent project_id correctly returns the documented 404.")

            # 4. Org A retains full working access after the fix (regression guard).
            print("\nTest 4: Verifying Org A retains full working access...")
            res = await client.get(f"/api/v1/context/projects/{project_a_id}/graph", headers=headers_a)
            assert res.status_code == 200
            print("SUCCESS: Org A retains full working access to its own project graph.")

        finally:
            print("\nCleaning up project knowledge graph test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    edge_res = await session.execute(select(KnowledgeGraphEdge).where(KnowledgeGraphEdge.organization_id == oid))
                    for e in edge_res.scalars().all():
                        await session.delete(e)
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

    print("\nAll Project Unified Knowledge Graph tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_project_knowledge_graph_flow())
