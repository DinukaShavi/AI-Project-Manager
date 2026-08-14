import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User, Role
from app.models.audit import AuditLog
from app.db.session import SessionLocal
from app.core.security import get_password_hash

async def test_role_management_flow():
    print("Initializing Role Management (grant/revoke) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    password = "MgmtPass123!"
    org_a_id = None
    org_b_id = None
    dev_user_id = None
    org_admin_id = None
    super_admin_id = None
    other_org_user_id = None

    dev_email = f"mgmt-dev-{suffix}@example.com"
    org_admin_email = f"mgmt-orgadmin-{suffix}@example.com"
    super_admin_email = f"mgmt-superadmin-{suffix}@example.com"
    other_org_email = f"mgmt-otherorg-{suffix}@example.com"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Mgmt Org A {suffix}", domain=f"mgmt-a-{suffix}.com")
                org_b = Organization(name=f"Mgmt Org B {suffix}", domain=f"mgmt-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id = org_a.id
                org_b_id = org_b.id

                org_admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                super_admin_role = (await session.execute(select(Role).where(Role.name == "SuperAdmin"))).scalar_one()

                org_admin = User(organization_id=org_a_id, email=org_admin_email, full_name="Org Admin", hashed_password=get_password_hash(password))
                org_admin.roles.append(org_admin_role)
                super_admin = User(organization_id=org_a_id, email=super_admin_email, full_name="Super Admin", hashed_password=get_password_hash(password))
                super_admin.roles.append(super_admin_role)
                other_org_user = User(organization_id=org_b_id, email=other_org_email, full_name="Other Org User", hashed_password=get_password_hash(password))

                session.add_all([org_admin, super_admin, other_org_user])
                await session.commit()
                await session.refresh(org_admin)
                await session.refresh(super_admin)
                await session.refresh(other_org_user)
                org_admin_id = org_admin.id
                super_admin_id = super_admin.id
                other_org_user_id = other_org_user.id
            print(f"Test orgs and seed admins created. OrgAdmin={org_admin_id} SuperAdmin={super_admin_id}")

            def headers_for(token: str) -> dict:
                return {"Authorization": f"Bearer {token}"}

            async def login(email: str) -> dict:
                res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
                assert res.status_code == 200, f"Login failed for {email}: {res.text}"
                return headers_for(res.json()["access_token"])

            # Register the target Developer user via the normal flow (gets default 'Developer').
            res = await client.post(
                "/api/v1/users/register",
                json={"email": dev_email, "full_name": "Target Dev", "organization_id": str(org_a_id), "password": password}
            )
            assert res.status_code == 201, f"Registration failed: {res.text}"
            dev_user_id = uuid.UUID(res.json()["id"])

            org_admin_headers = await login(org_admin_email)
            super_admin_headers = await login(super_admin_email)
            dev_headers = await login(dev_email)
            other_org_headers = await login(other_org_email)

            # 1. A non-admin (Developer) cannot grant roles.
            print("\nTest 1: Verifying a Developer-role actor is denied role management (403)...")
            res = await client.post(
                f"/api/v1/users/{dev_user_id}/roles", json={"role_name": "ProjectManager"}, headers=dev_headers
            )
            assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
            print("SUCCESS: Non-admin actor correctly denied.")

            # 2. An OrgAdmin can grant a non-SuperAdmin role within their own org.
            print("\nTest 2: Verifying OrgAdmin can grant 'ProjectManager' to a same-org user...")
            res = await client.post(
                f"/api/v1/users/{dev_user_id}/roles", json={"role_name": "ProjectManager"}, headers=org_admin_headers
            )
            assert res.status_code == 200, f"Grant failed: {res.text}"
            assert set(res.json()["roles"]) == {"Developer", "ProjectManager"}
            print("SUCCESS: Role granted; user now holds both Developer and ProjectManager.")

            # 3. Granting the same role again is idempotent (no duplicate, no error).
            print("\nTest 3: Verifying re-granting the same role is idempotent...")
            res = await client.post(
                f"/api/v1/users/{dev_user_id}/roles", json={"role_name": "ProjectManager"}, headers=org_admin_headers
            )
            assert res.status_code == 200
            assert res.json()["roles"].count("ProjectManager") == 1
            print("SUCCESS: Re-granting did not duplicate the role assignment.")

            # 4. An OrgAdmin (not SuperAdmin) cannot grant SuperAdmin — privilege escalation guard.
            print("\nTest 4: Verifying a mere OrgAdmin cannot grant 'SuperAdmin' (403)...")
            res = await client.post(
                f"/api/v1/users/{dev_user_id}/roles", json={"role_name": "SuperAdmin"}, headers=org_admin_headers
            )
            assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
            print("SUCCESS: OrgAdmin correctly blocked from granting SuperAdmin.")

            # 5. A SuperAdmin CAN grant SuperAdmin.
            print("\nTest 5: Verifying a SuperAdmin CAN grant 'SuperAdmin'...")
            res = await client.post(
                f"/api/v1/users/{dev_user_id}/roles", json={"role_name": "SuperAdmin"}, headers=super_admin_headers
            )
            assert res.status_code == 200, f"Grant failed: {res.text}"
            assert "SuperAdmin" in res.json()["roles"]
            print("SUCCESS: SuperAdmin actor successfully granted SuperAdmin.")

            # 6. Cross-tenant isolation: an admin cannot manage a user in a different organization.
            print("\nTest 6: Verifying cross-tenant role management is denied...")
            res = await client.post(
                f"/api/v1/users/{other_org_user_id}/roles", json={"role_name": "ProjectManager"}, headers=org_admin_headers
            )
            assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
            print("SUCCESS: Cross-tenant role management correctly denied.")

            # 7. Revoking a role removes it (and is idempotent).
            print("\nTest 7: Verifying role revocation...")
            res = await client.delete(f"/api/v1/users/{dev_user_id}/roles/ProjectManager", headers=org_admin_headers)
            assert res.status_code == 200, f"Revoke failed: {res.text}"
            assert "ProjectManager" not in res.json()["roles"]

            res = await client.delete(f"/api/v1/users/{dev_user_id}/roles/ProjectManager", headers=org_admin_headers)
            assert res.status_code == 200, f"Idempotent revoke failed: {res.text}"
            print("SUCCESS: Role revoked and revocation is idempotent.")

            # 8. Both grant and revoke actions were audit-logged.
            print("\nTest 8: Verifying role grant/revoke actions were audit-logged...")
            async with SessionLocal() as session:
                result = await session.execute(
                    select(AuditLog).where(AuditLog.organization_id == org_a_id, AuditLog.action.in_(["role:grant", "role:revoke"]))
                )
                logs = result.scalars().all()
                assert any(l.action == "role:grant" for l in logs), "Expected at least one 'role:grant' audit entry"
                assert any(l.action == "role:revoke" for l in logs), "Expected at least one 'role:revoke' audit entry"
            print(f"SUCCESS: {len(logs)} role management audit entries recorded.")

        finally:
            print("\nCleaning up role management test database entries...")
            async with SessionLocal() as session:
                for uid in [u for u in [dev_user_id, org_admin_id, super_admin_id, other_org_user_id] if u]:
                    result = await session.execute(select(User).where(User.id == uid))
                    u = result.scalar_one_or_none()
                    if u:
                        await session.delete(u)
                await session.commit()

                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    result = await session.execute(select(Organization).where(Organization.id == oid))
                    db_org = result.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Role Management tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_role_management_flow())
