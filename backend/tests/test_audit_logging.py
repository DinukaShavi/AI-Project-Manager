import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization
from app.models.audit import AuditLog
from app.db.session import SessionLocal

async def test_audit_logging_flow():
    print("Initializing Audit Logging validation tests...")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    email = f"audit-test-{suffix}@example.com"
    password = "AuditPass123!"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create a test organization
            async with SessionLocal() as session:
                org = Organization(name=f"Audit Test Org {suffix}", domain=f"audit-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            # 1. Registration should write an 'auth:register' audit_logs entry
            print("\nTest 1: Verifying POST /users/register writes an audit_logs entry...")
            res = await client.post(
                "/api/v1/users/register",
                json={"email": email, "full_name": "Audit Test User", "organization_id": str(test_org_id), "password": password}
            )
            assert res.status_code == 201, f"Registration failed: {res.text}"
            user_id = uuid.UUID(res.json()["id"])

            async with SessionLocal() as session:
                result = await session.execute(
                    select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "auth:register")
                )
                register_log = result.scalar_one_or_none()
                assert register_log is not None, "Expected an 'auth:register' audit_logs row"
                assert register_log.organization_id == test_org_id
                assert register_log.details.get("email") == email
            print("SUCCESS: Registration audit entry persisted correctly.")

            # 2. Failed login (wrong password) should write an 'auth:login_failed' entry
            print("\nTest 2: Verifying a failed login writes 'auth:login_failed'...")
            res = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword!"})
            assert res.status_code == 400, f"Expected login rejection, got {res.status_code}: {res.text}"

            async with SessionLocal() as session:
                result = await session.execute(
                    select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "auth:login_failed")
                )
                failed_log = result.scalar_one_or_none()
                assert failed_log is not None, "Expected an 'auth:login_failed' audit_logs row"
            print("SUCCESS: Failed login audit entry persisted correctly.")

            # 3. Successful login should write an 'auth:login_success' entry
            print("\nTest 3: Verifying a successful login writes 'auth:login_success'...")
            res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
            assert res.status_code == 200, f"Login failed: {res.text}"
            auth_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

            async with SessionLocal() as session:
                result = await session.execute(
                    select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "auth:login_success")
                )
                success_log = result.scalar_one_or_none()
                assert success_log is not None, "Expected an 'auth:login_success' audit_logs row"
            print("SUCCESS: Successful login audit entry persisted correctly.")

            # 4. Tool execution should write a 'tool:execute' entry
            print("\nTest 4: Verifying POST /tools/execute writes 'tool:execute'...")
            res = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "context_search", "parameters": {"organization_id": str(test_org_id), "query": "audit logging", "top_k": 1}},
                headers=auth_headers
            )
            assert res.status_code == 200, f"Tool execution failed: {res.text}"

            async with SessionLocal() as session:
                result = await session.execute(
                    select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "tool:execute")
                )
                tool_logs = result.scalars().all()
                assert any(l.details.get("tool_name") == "context_search" for l in tool_logs), \
                    "Expected a 'tool:execute' audit_logs row for context_search"
            print("SUCCESS: Tool execution audit entry persisted correctly.")

            # 5. A gated (WAITING_APPROVAL) high-risk tool call must ALSO be audited, not just successful ones
            print("\nTest 5: Verifying a HITL-suspended tool call still writes 'tool:execute'...")
            res = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "merge_pull_request", "parameters": {"pr_number": 7}},
                headers=auth_headers
            )
            assert res.status_code == 200
            assert res.json()["status"] == "waiting_approval"

            async with SessionLocal() as session:
                result = await session.execute(
                    select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "tool:execute")
                )
                tool_logs = result.scalars().all()
                assert any(
                    l.details.get("tool_name") == "merge_pull_request" and l.details.get("status") == "WAITING_APPROVAL"
                    for l in tool_logs
                ), "Expected a WAITING_APPROVAL 'tool:execute' audit_logs row for merge_pull_request"
            print("SUCCESS: HITL-suspended tool call was still audited, not silently skipped.")

            # 6. Workflow execution should write a 'workflow:execute' entry
            print("\nTest 6: Verifying POST /workflows/execute writes 'workflow:execute'...")
            res = await client.post(
                "/api/v1/workflows/execute",
                json={"template": "architecture_audit", "initial_context": {"component": "AuditService"}},
                headers=auth_headers
            )
            assert res.status_code == 200, f"Workflow execution failed: {res.text}"

            async with SessionLocal() as session:
                result = await session.execute(
                    select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "workflow:execute")
                )
                workflow_log = result.scalar_one_or_none()
                assert workflow_log is not None, "Expected a 'workflow:execute' audit_logs row"
                assert workflow_log.details.get("status") == "completed"
            print("SUCCESS: Workflow execution audit entry persisted correctly.")

        finally:
            print("\nCleaning up audit logging test database entries...")
            async with SessionLocal() as session:
                if test_org_id:
                    result = await session.execute(select(AuditLog).where(AuditLog.organization_id == test_org_id))
                    for log_row in result.scalars().all():
                        await session.delete(log_row)
                    await session.commit()

                    result = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = result.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                    await session.commit()
            print("Cleanup completed.")

    print("\nAll Audit Logging tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_audit_logging_flow())
