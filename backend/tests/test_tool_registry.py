import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization
from app.models.agent import AgentExecution, ToolExecution
from app.tools.registry import get_tool_registry
from app.services.tool import ToolService
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

async def test_tool_registry_flow():
    print("Initializing Tool Registry validation tests...")

    # 1. Test Registry Discovery
    print("\nTest 1: Testing ToolRegistry tool registration and schema discovery...")
    registry = get_tool_registry()
    tools_list = registry.list_tools()
    tool_names = [t["name"] for t in tools_list]
    assert len(tools_list) >= 6
    assert "github_create_issue" in tool_names
    assert "jira_get_issue" in tool_names
    assert "slack_post_message" in tool_names
    assert "context_search" in tool_names
    print(f"SUCCESS: ToolRegistry discovered {len(tools_list)} tools: {tool_names}")

    # 2. Test Parameter Schema Validation and Tool Execution
    print("\nTest 2: Testing tool execution and parameter schema validation...")
    gh_tool = registry.get_tool("github_create_issue")
    # No session and no connected GitHub integration for this org — the tool must degrade
    # gracefully to a clear "not connected" error rather than crash or fabricate a fake issue.
    res_gh = await gh_tool.execute({"organization_id": str(uuid.uuid4()), "repo": "acme/ai-tpm", "title": "Add Tool Registry"})
    assert res_gh["status"] == "error"
    assert "session" in res_gh["message"].lower() or "not connected" in res_gh["message"].lower()

    jira_tool = registry.get_tool("jira_get_issue")
    # Jira uses a static instance-wide API token (settings.JIRA_*), unconfigured in this
    # environment — must degrade gracefully while still echoing back the requested issue_key.
    res_jira = await jira_tool.execute({"issue_key": "TPM-101"})
    assert res_jira["issue_key"] == "TPM-101"
    assert res_jira["status"] == "error"

    # Test missing required parameter validation exception
    try:
        await gh_tool.execute({"title": "Missing repo"})
        assert False, "Expected ValueError for missing parameter 'repo'"
    except ValueError as e:
        print(f"SUCCESS: Parameter validation correctly caught missing field: {e}")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    test_agent_exec_id = None
    created_tool_exec_ids = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization and agent execution record in DB
            async with SessionLocal() as session:
                print("\nInserting test organization and agent execution database entries...")
                org = Organization(name=f"Tool Test Org {suffix}", domain=f"tool-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id

                agent_exec = AgentExecution(
                    organization_id=org.id,
                    agent_name="TechnicalPMAgent",
                    agent_role="Technical PM",
                    status="completed"
                )
                session.add(agent_exec)
                await session.commit()
                test_agent_exec_id = agent_exec.id
                print(f"Test Organization & AgentExecution created. AgentExec ID: {agent_exec.id}")

            # 3. Test ToolService DB Audit Logging
            print("\nTest 3: Testing ToolService DB audit logging...")
            async with SessionLocal() as session:
                service = ToolService(session)
                # No Slack integration is connected for this fresh test org, so the tool call
                # itself reports a business-level "error" (not connected) — but it does not
                # raise, so ToolService still logs a "success" (i.e. "didn't crash") audit row.
                res = await service.execute_tool(
                    tool_name="slack_post_message",
                    parameters={"organization_id": str(test_org_id), "channel": "#dev-alerts", "message": "Phase 7 Tool Registry Complete!"},
                    agent_execution_id=test_agent_exec_id
                )
                assert res["status"] == "error"
                assert "not connected" in res["error"].lower()

                # Verify ToolExecution record in PostgreSQL DB
                db_res = await session.execute(
                    select(ToolExecution).where(ToolExecution.agent_execution_id == test_agent_exec_id)
                )
                tool_exec = db_res.scalar_one()
                created_tool_exec_ids.append(tool_exec.id)
                assert tool_exec.tool_name == "slack_post_message"
                assert tool_exec.status == "success"
                print(f"SUCCESS: ToolExecution logged in DB even though the underlying Slack call correctly reported 'not connected'.")

            auth_headers = await create_authenticated_headers(client, test_org_id)

            # 4. Test HTTP API Endpoint: GET /api/v1/tools
            print("\nTest 4: Requesting GET /api/v1/tools...")
            res = await client.get("/api/v1/tools", headers=auth_headers)
            assert res.status_code == 200, f"Endpoint failed: {res.text}"
            tools_json = res.json()
            assert tools_json["tools_count"] >= 6
            print(f"SUCCESS: GET /tools returned {tools_json['tools_count']} tools.")

            # 5. Test HTTP API Endpoint: POST /api/v1/tools/execute
            print("\nTest 5: Requesting POST /api/v1/tools/execute...")
            res = await client.post(
                "/api/v1/tools/execute",
                json={
                    "tool_name": "context_search",
                    "parameters": {"organization_id": str(test_org_id), "query": "database schema migration", "top_k": 3},
                    "agent_execution_id": str(test_agent_exec_id)
                },
                headers=auth_headers
            )
            assert res.status_code == 200, f"Endpoint failed: {res.text}"
            exec_json = res.json()
            assert exec_json["status"] == "success"
            assert exec_json["tool_name"] == "context_search"
            print("SUCCESS: HTTP tool execution completed successfully.")

            # 6. Test HITL Approval Gate: high-risk tool without approval_token must suspend, not execute
            print("\nTest 6: Requesting POST /api/v1/tools/execute for a high-risk tool with no approval_token...")
            res = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "merge_pull_request", "parameters": {"pr_number": 42}},
                headers=auth_headers
            )
            assert res.status_code == 200, f"Endpoint failed: {res.text}"
            gate_json = res.json()
            assert gate_json["status"] == "waiting_approval", f"Expected HITL suspension, got: {gate_json}"
            assert "approval_id" in gate_json
            print("SUCCESS: High-risk tool call correctly suspended pending human approval, not executed.")

            # 7. Test HITL Approval Gate: supplying approval_token bypasses suspension and proceeds to execution
            print("\nTest 7: Requesting POST /api/v1/tools/execute for the same tool WITH an approval_token...")
            res = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "merge_pull_request", "parameters": {"pr_number": 42}, "approval_token": "approved-by-test"},
                headers=auth_headers
            )
            # merge_pull_request is not a registered tool in this codebase (only github/jira/slack/context tools
            # are), so a granted approval correctly reaches tool discovery and 404s there — proving the approval
            # gate itself was bypassed rather than re-suspending, without fabricating a successful execution for
            # a tool that doesn't actually exist.
            assert res.status_code == 404, f"Expected tool-not-found after approval, got {res.status_code}: {res.text}"
            print("SUCCESS: Approval token correctly bypassed the HITL gate and reached tool execution.")

        finally:
            # Clean up database records
            print("\nCleaning up tool registry test database entries...")
            async with SessionLocal() as session:
                if test_agent_exec_id:
                    res = await session.execute(select(ToolExecution).where(ToolExecution.agent_execution_id == test_agent_exec_id))
                    t_execs = res.scalars().all()
                    for t in t_execs:
                        await session.delete(t)
                    res = await session.execute(select(AgentExecution).where(AgentExecution.id == test_agent_exec_id))
                    a_exec = res.scalar_one_or_none()
                    if a_exec:
                        await session.delete(a_exec)
                if test_org_id:
                    res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Tool Registry tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_tool_registry_flow())
