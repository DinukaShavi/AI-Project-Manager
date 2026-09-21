import asyncio
import uuid
from unittest.mock import patch
from sqlalchemy import select

import app.db.base  # Register models
from app.models.tenant import Organization, Workspace
from app.models.project import Project, Repository
from app.models.agent import AgentExecution
from app.agents.base import BaseAgent
from app.services.context_ingestion import ContextIngestionService
from app.services.intelligence_engine import ProjectIntelligenceEngine
from app.db.session import SessionLocal


async def test_real_agent_step_execution_flow():
    print("Initializing Real Agent Step Execution (Phase 69) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    ingestion_service = ContextIngestionService()
    repo_name = f"acme/plan-{suffix}"

    org_id = None
    project_id = None
    created_execution_ids = []

    try:
        async with SessionLocal() as session:
            org = Organization(name=f"Real Plan Org {suffix}", domain=f"realplan-{suffix}.com")
            session.add(org)
            await session.flush()
            org_id = org.id

            workspace = Workspace(organization_id=org_id, name="Real Plan Workspace")
            session.add(workspace)
            await session.flush()

            project = Project(organization_id=org_id, workspace_id=workspace.id, name="Real Plan Project")
            session.add(project)
            await session.flush()
            project_id = project.id

            repo = Repository(organization_id=org_id, project_id=project_id, external_repo_id="1", name=repo_name, clone_url=f"https://github.com/{repo_name}.git")
            session.add(repo)
            await session.commit()
        print(f"Test org/project created. Org={org_id} Project={project_id}")

        # Seed real context: a real GitHub event indexed for this project, so the assembled
        # context has real search results and a real snapshot to draw from.
        gh_payload = {
            "organization_id": str(org_id), "project_id": None,
            "payload": {
                "provider": "github", "repository": repo_name,
                "raw_payload": {
                    "action": "opened",
                    "issue": {"number": 1, "title": "Login race condition under load", "body": "Users report intermittent failures.", "html_url": "https://github.com/x"},
                    "repository": {"full_name": repo_name},
                },
            },
        }
        await ingestion_service.handle_event("plan1", gh_payload)

        # A second real, distinct event -- gives the grounding search's real reranking call
        # (Phase 82) more than one real candidate to actually reorder (reranking correctly
        # no-ops on a single-candidate result set, per Phase 78's own design).
        gh_payload_2 = {
            "organization_id": str(org_id), "project_id": None,
            "payload": {
                "provider": "github", "repository": repo_name,
                "raw_payload": {
                    "action": "opened",
                    "issue": {"number": 2, "title": "Auth token refresh fails intermittently", "body": "Related to session expiry under load.", "html_url": "https://github.com/y"},
                    "repository": {"full_name": repo_name},
                },
            },
        }
        await ingestion_service.handle_event("plan1b", gh_payload_2)

        # 1. A real process_goal run (real db session) creates real, queryable AgentExecution
        #    rows per non-tool step -- not a synthetic inline dict. Also verifies the
        #    grounding search's real reranking call (Phase 82) is genuinely triggered, by
        #    wrapping (not replacing) the real _llm_call and counting calls whose system
        #    prompt is the reranker's -- every other call still runs its real fallback chain
        #    unchanged.
        print("\nTest 1: Verifying process_goal with a real db session creates real AgentExecution rows...")
        original_llm_call = BaseAgent._llm_call
        rerank_call_count = {"n": 0}

        async def counting_llm_call(self, prompt, system_prompt, task_category="output_reflection"):
            if "rerank" in system_prompt.lower():
                rerank_call_count["n"] += 1
            return await original_llm_call(self, prompt, system_prompt, task_category)

        with patch.object(BaseAgent, "_llm_call", new=counting_llm_call):
            async with SessionLocal() as session:
                engine = ProjectIntelligenceEngine(session)
                result = await engine.process_goal(
                    goal="Audit sprint delivery and architecture compliance",
                    organization_id=str(org_id),
                    project_id=str(project_id),
                    user_role="Developer",
                )
        assert rerank_call_count["n"] >= 1, "Expected the grounding search's real reranking call to be triggered (Phase 82)"

        executed_steps = result["plan_execution"]["executed_steps"]
        agent_steps = [s for s in executed_steps if s["type"] != "tool"]
        assert len(agent_steps) > 0, "Expected at least one real agent step"
        for s in agent_steps:
            assert "agent_execution_id" in s["result"], f"Expected a real agent_execution_id, got: {s['result']}"
            assert s["result"]["status"] in ("SUCCESS", "FAILURE")
            assert "Synthetic reasoning analysis completed" not in str(s["result"]), "The old synthetic placeholder must not appear when a real db session is used"
            created_execution_ids.append(uuid.UUID(s["result"]["agent_execution_id"]))
        print(f"SUCCESS: {len(agent_steps)} real agent step(s) executed via the real AgentService path.")

        # 2. Each of those AgentExecution rows is real and queryable, with real output.
        print("\nTest 2: Verifying the AgentExecution rows are real and persisted...")
        async with SessionLocal() as session:
            for exec_id in created_execution_ids:
                res = await session.execute(select(AgentExecution).where(AgentExecution.id == exec_id))
                row = res.scalar_one_or_none()
                assert row is not None, f"Expected a real persisted AgentExecution for {exec_id}"
                assert row.organization_id == org_id
                assert row.status == "COMPLETED"
                assert row.output_payload is not None and "analysis" in row.output_payload
        print("SUCCESS: Real AgentExecution rows correctly persisted with real output.")

        # 3. The no-db fallback path is preserved unchanged -- ProjectIntelligenceEngine()
        #    with no session still returns the synthetic placeholder, proving this phase
        #    didn't silently break the existing unit-test contract.
        print("\nTest 3: Verifying the no-db fallback path is unchanged...")
        engine_no_db = ProjectIntelligenceEngine()
        result_no_db = await engine_no_db.process_goal(
            goal="Audit sprint delivery",
            organization_id=str(org_id),
        )
        no_db_agent_steps = [s for s in result_no_db["plan_execution"]["executed_steps"] if s["type"] != "tool"]
        assert len(no_db_agent_steps) > 0
        assert all("Synthetic reasoning analysis completed" in s["result"]["result"]["analysis"] for s in no_db_agent_steps)
        print("SUCCESS: No-db fallback path correctly preserved (still synthetic, by design).")

    finally:
        print("\nCleaning up test database entries...")
        async with SessionLocal() as session:
            from app.models.tenant import User
            from app.models.context import ContextChunk, ContextEmbedding
            from app.models.graph import ContextSnapshot, KnowledgeGraphEdge
            from app.models.recommendation import Recommendation
            for exec_id in created_execution_ids:
                res = await session.execute(select(AgentExecution).where(AgentExecution.id == exec_id))
                row = res.scalar_one_or_none()
                if row:
                    await session.delete(row)
            await session.flush()
            if project_id:
                for model in (ContextSnapshot, KnowledgeGraphEdge, Recommendation, Repository):
                    res = await session.execute(select(model).where(model.project_id == project_id))
                    for row in res.scalars().all():
                        await session.delete(row)
                await session.flush()
                res = await session.execute(select(ContextEmbedding).join(ContextChunk).where(ContextChunk.project_id == project_id))
                for row in res.scalars().all():
                    await session.delete(row)
                await session.flush()
                res = await session.execute(select(ContextChunk).where(ContextChunk.project_id == project_id))
                for row in res.scalars().all():
                    await session.delete(row)
                await session.flush()
                res = await session.execute(select(Project).where(Project.id == project_id))
                p = res.scalar_one_or_none()
                if p:
                    await session.delete(p)
            await session.flush()
            if org_id:
                res = await session.execute(select(Workspace).where(Workspace.organization_id == org_id))
                for w in res.scalars().all():
                    await session.delete(w)
                res = await session.execute(select(User).where(User.organization_id == org_id))
                for u in res.scalars().all():
                    await session.delete(u)
                await session.flush()
                org_row = await session.get(Organization, org_id)
                if org_row:
                    await session.delete(org_row)
            await session.commit()
        print("Cleanup completed.")

    print("\nAll Real Agent Step Execution tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_real_agent_step_execution_flow())
