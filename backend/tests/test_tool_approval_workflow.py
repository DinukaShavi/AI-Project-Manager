import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base  # Register models
from app.main import app
from app.models.tenant import Organization, User, Role
from app.models.agent import ToolApproval
from app.db.session import SessionLocal
from app.core.security import get_password_hash
from app.services.tool_approval import ToolApprovalService
from tests._auth_helpers import create_authenticated_headers

PASSWORD = "ApprovalPass123!"


async def _make_user(org_id, role_name: str, label: str) -> str:
    """Create a real user in `org_id` holding `role_name`, returning their email."""
    email = f"{label}-{uuid.uuid4().hex[:8]}@example.com"
    async with SessionLocal() as session:
        role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one()
        user = User(
            organization_id=org_id,
            email=email,
            full_name=f"{role_name} {label}",
            hashed_password=get_password_hash(PASSWORD),
        )
        user.roles.append(role)
        session.add(user)
        await session.commit()
    return email


async def _login(client: AsyncClient, email: str) -> dict:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def test_tool_approval_workflow_flow():
    print("Initializing Real Human-in-the-Loop Tool Approval (Phase 86) validation tests...")

    org_a_id = None
    org_b_id = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Approval Org A {uuid.uuid4().hex[:6]}", domain=f"appr-a-{uuid.uuid4().hex[:6]}.com")
                org_b = Organization(name=f"Approval Org B {uuid.uuid4().hex[:6]}", domain=f"appr-b-{uuid.uuid4().hex[:6]}.com")
                session.add_all([org_a, org_b])
                await session.commit()
                org_a_id = org_a.id
                org_b_id = org_b.id

            # The requester is a plain Developer -- authorized by the PDP to *request*
            # merge_pull_request, but never to sign off on it.
            dev_headers = await create_authenticated_headers(client, org_a_id)
            merge_params = {"repo": "acme/ai-tpm", "pr_number": 42}

            # 1. The pre-Phase-86 bypass must be gone: an invented token is refused.
            print("\nTest 1: Verifying an arbitrary/forged approval_token is rejected...")
            for forged in ("approved-by-test", str(uuid.uuid4()), "x"):
                res = await client.post(
                    "/api/v1/tools/execute",
                    json={"tool_name": "merge_pull_request", "parameters": merge_params, "approval_token": forged},
                    headers=dev_headers,
                )
                assert res.status_code == 403, (
                    f"Forged approval token {forged!r} was NOT rejected (got {res.status_code}: {res.text}). "
                    "The human-in-the-loop gate is bypassable."
                )
            print("SUCCESS: Forged approval tokens are rejected with 403; the old any-string bypass is closed.")

            # 2. A high-risk call with no token creates a real, persisted pending record.
            print("\nTest 2: Verifying an unapproved high-risk call persists a real pending approval...")
            res = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "merge_pull_request", "parameters": merge_params},
                headers=dev_headers,
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["status"] == "waiting_approval", body
            approval_id = body["approval_id"]

            async with SessionLocal() as session:
                row = await session.get(ToolApproval, uuid.UUID(approval_id))
                assert row is not None, "approval_id was returned but no ToolApproval row exists (the pre-Phase-86 defect)."
                assert row.status == "pending"
                assert row.tool_name == "merge_pull_request"
                assert row.organization_id == org_a_id
                assert row.approval_token_hash is None, "No token may exist before a human approves."
            print("SUCCESS: A real pending ToolApproval row was persisted and is visible by id.")

            # It also shows up on the approvals queue the M12 UI renders.
            res_q = await client.get("/api/v1/tools/approvals", headers=dev_headers)
            assert res_q.status_code == 200, res_q.text
            assert any(a["approval_id"] == approval_id for a in res_q.json()["approvals"])

            # 3. A Developer may not approve; four-eyes blocks self-approval even for admins.
            print("\nTest 3: Verifying approval authority and the four-eyes rule...")
            res_self = await client.post(f"/api/v1/tools/approve/{approval_id}", headers=dev_headers)
            assert res_self.status_code == 403, f"A Developer must not be able to approve: {res_self.text}"

            # Same user, now elevated to SuperAdmin: still refused, because they requested it.
            async with SessionLocal() as session:
                requester = (await session.execute(
                    select(User).where(User.organization_id == org_a_id)
                )).scalars().first()
                sa_role = (await session.execute(select(Role).where(Role.name == "SuperAdmin"))).scalar_one()
                requester_fresh = await session.get(User, requester.id)
                await session.refresh(requester_fresh, attribute_names=["roles"])
                requester_fresh.roles.append(sa_role)
                await session.commit()

            res_self_admin = await client.post(f"/api/v1/tools/approve/{approval_id}", headers=dev_headers)
            assert res_self_admin.status_code == 403, (
                f"Four-eyes violated: the requester approved their own high-risk call: {res_self_admin.text}"
            )
            assert "own request" in res_self_admin.json()["detail"].lower()
            print("SUCCESS: Developers cannot approve, and a requester cannot self-approve even as SuperAdmin.")

            # 4. A real, different ProjectManager can approve merge_pull_request.
            print("\nTest 4: Verifying a qualified, different approver can grant the request...")
            pm_email = await _make_user(org_a_id, "ProjectManager", "pm")
            pm_headers = await _login(client, pm_email)

            res_ok = await client.post(f"/api/v1/tools/approve/{approval_id}", headers=pm_headers)
            assert res_ok.status_code == 200, res_ok.text
            token = res_ok.json()["approval_token"]
            assert token and len(token) >= 20

            async with SessionLocal() as session:
                row = await session.get(ToolApproval, uuid.UUID(approval_id))
                assert row.status == "approved"
                assert row.approval_token_hash is not None
                assert row.approval_token_hash != token, "The raw token must never be stored; only its hash."
            print("SUCCESS: A ProjectManager granted the request; only the token's hash is stored.")

            # 5. The grant is bound to the exact parameters it was issued for.
            print("\nTest 5: Verifying an approved token cannot be replayed against different parameters...")
            res_swap = await client.post(
                "/api/v1/tools/execute",
                json={
                    "tool_name": "merge_pull_request",
                    "parameters": {"repo": "acme/ai-tpm", "pr_number": 999},  # different PR
                    "approval_token": token,
                },
                headers=dev_headers,
            )
            assert res_swap.status_code == 403, f"Parameter swap was NOT blocked: {res_swap.text}"
            assert "different parameters" in res_swap.json()["detail"].lower()
            print("SUCCESS: A token approved for PR #42 cannot merge PR #999.")

            # 6. The grant is tenant-scoped.
            print("\nTest 6: Verifying Org A's approval token is useless in Org B...")
            org_b_headers = await create_authenticated_headers(client, org_b_id)
            res_cross = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "merge_pull_request", "parameters": merge_params, "approval_token": token},
                headers=org_b_headers,
            )
            assert res_cross.status_code == 403, f"Cross-tenant approval reuse was NOT blocked: {res_cross.text}"
            print("SUCCESS: An approval granted in Org A cannot authorize an identical call in Org B.")

            # 7. The correct call executes for real, exactly once.
            print("\nTest 7: Verifying the approved call executes, then cannot be replayed...")
            res_exec = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "merge_pull_request", "parameters": merge_params, "approval_token": token},
                headers=dev_headers,
            )
            assert res_exec.status_code == 200, res_exec.text
            # No GitHub integration is connected for this fresh org, so the real connector
            # correctly reports "not connected" rather than fabricating a merge -- the point
            # here is that the gate was passed and real execution was attempted.
            assert res_exec.json()["status"] == "error"
            assert "not connected" in res_exec.json()["output"]["message"].lower()

            async with SessionLocal() as session:
                row = await session.get(ToolApproval, uuid.UUID(approval_id))
                assert row.status == "consumed", f"Expected single-use consumption, got '{row.status}'."
                assert row.consumed_at is not None

            res_replay = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "merge_pull_request", "parameters": merge_params, "approval_token": token},
                headers=dev_headers,
            )
            assert res_replay.status_code == 403, f"Token replay was NOT blocked: {res_replay.text}"
            print("SUCCESS: The approved call ran once and the token cannot be replayed.")

            # 8. delete_repository requires a SuperAdmin specifically (spec section 5).
            print("\nTest 8: Verifying delete_repository needs SuperAdmin, not merely a PM...")
            async with SessionLocal() as session:
                sa_role = (await session.execute(select(Role).where(Role.name == "SuperAdmin"))).scalar_one()
                admin_user = User(
                    organization_id=org_a_id,
                    email=f"sa-{uuid.uuid4().hex[:8]}@example.com",
                    full_name="Real SuperAdmin",
                    hashed_password=get_password_hash(PASSWORD),
                )
                admin_user.roles.append(sa_role)
                session.add(admin_user)
                await session.commit()
                admin_email = admin_user.email
            admin_headers = await _login(client, admin_email)

            # The SuperAdmin requests it (a Developer would be denied outright by the PDP).
            res_del = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "delete_repository", "parameters": {"repo": "acme/old"}},
                headers=admin_headers,
            )
            assert res_del.status_code == 200, res_del.text
            del_approval_id = res_del.json()["approval_id"]

            # The PM may not approve a SuperAdmin-only tool.
            res_pm_del = await client.post(f"/api/v1/tools/approve/{del_approval_id}", headers=pm_headers)
            assert res_pm_del.status_code == 403, f"A PM must not approve delete_repository: {res_pm_del.text}"
            print("SUCCESS: delete_repository approval is restricted to SuperAdmin per spec section 5.")

            # 9. Expired grants are refused.
            print("\nTest 9: Verifying an expired approval is rejected...")
            async with SessionLocal() as session:
                expired = ToolApproval(
                    organization_id=org_a_id,
                    tool_name="merge_pull_request",
                    tool_parameters=merge_params,
                    parameters_fingerprint=ToolApprovalService.fingerprint_parameters(merge_params),
                    status="approved",
                    approval_token_hash=hashlib.sha256(b"expired-token").hexdigest(),
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                )
                session.add(expired)
                await session.commit()

            res_expired = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "merge_pull_request", "parameters": merge_params, "approval_token": "expired-token"},
                headers=dev_headers,
            )
            assert res_expired.status_code == 403, f"Expired approval was NOT rejected: {res_expired.text}"
            assert "expired" in res_expired.json()["detail"].lower()
            print("SUCCESS: Expired approval grants are rejected.")

            # 10. Low-risk tools are untouched by any of this.
            print("\nTest 10: Verifying low-risk tools still need no approval...")
            res_low = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "context_search", "parameters": {"query": "sprint status", "top_k": 2}},
                headers=dev_headers,
            )
            assert res_low.status_code == 200, res_low.text
            assert res_low.json()["status"] == "success"
            print("SUCCESS: Low-risk tool execution is unaffected.")

        finally:
            print("\nCleaning up tool approval test database entries...")
            for org_id in (org_a_id, org_b_id):
                if not org_id:
                    continue
                async with SessionLocal() as session:
                    approvals = await session.execute(select(ToolApproval).where(ToolApproval.organization_id == org_id))
                    for a in approvals.scalars().all():
                        await session.delete(a)
                    users = await session.execute(select(User).where(User.organization_id == org_id))
                    for u in users.scalars().all():
                        await session.delete(u)
                    org_row = await session.get(Organization, org_id)
                    if org_row:
                        await session.delete(org_row)
                    await session.commit()
            print("Cleanup completed.")

    print("\nAll Real Human-in-the-Loop Tool Approval tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_tool_approval_workflow_flow())
