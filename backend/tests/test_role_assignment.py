import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User, Role
from app.db.session import SessionLocal
from app.core.security import get_password_hash

async def test_role_assignment_flow():
    print("Initializing Role Assignment & RBAC Differentiation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    dev_email = f"dev-role-{suffix}@example.com"
    admin_email = f"admin-role-{suffix}@example.com"
    password = "RolePass123!"
    admin_user_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org = Organization(name=f"Role Test Org {suffix}", domain=f"role-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id
                await session.commit()
                print(f"Test Organization created. ID: {org.id}")

            # 1. The seed migration must have populated the 5 canonical roles matching
            # app.core.rbac_pdp.UserRole exactly.
            print("\nTest 1: Verifying default roles were seeded by the migration...")
            async with SessionLocal() as session:
                result = await session.execute(select(Role.name))
                names = {r for (r,) in result.all()}
                for expected in ("SuperAdmin", "OrgAdmin", "ProjectManager", "Developer", "Viewer"):
                    assert expected in names, f"Expected seeded role '{expected}' not found. Have: {names}"
            print("SUCCESS: All 5 canonical roles present in the database.")

            # 2. Registering a new user must auto-assign the default 'Developer' role.
            print("\nTest 2: Verifying registration auto-assigns the 'Developer' role...")
            res = await client.post(
                "/api/v1/users/register",
                json={"email": dev_email, "full_name": "Dev Role User", "organization_id": str(test_org_id), "password": password}
            )
            assert res.status_code == 201, f"Registration failed: {res.text}"
            dev_user_id = uuid.UUID(res.json()["id"])

            async with SessionLocal() as session:
                result = await session.execute(select(User).where(User.id == dev_user_id))
                dev_user = result.scalar_one()
                await session.refresh(dev_user, attribute_names=["roles"])
                role_names = {r.name for r in dev_user.roles}
                assert role_names == {"Developer"}, f"Expected exactly ['Developer'], got {role_names}"
            print("SUCCESS: New registrant was auto-assigned the 'Developer' role.")

            # 3. RBAC must actually differentiate: a Developer-role user is NOT authorized
            # for 'delete_repository' (SuperAdmin-only per the Tool Permission Matrix).
            print("\nTest 3: Verifying a Developer-role user is denied a SuperAdmin-only tool...")
            res = await client.post("/api/v1/auth/login", json={"email": dev_email, "password": password})
            assert res.status_code == 200, f"Login failed: {res.text}"
            dev_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

            res = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "delete_repository", "parameters": {}},
                headers=dev_headers
            )
            assert res.status_code == 403, f"Expected Developer role to be denied, got {res.status_code}: {res.text}"
            print("SUCCESS: Developer-role user correctly denied a SuperAdmin-only tool (403).")

            # 4. A SuperAdmin-role user must NOT be denied by the same RBAC check — proving the
            # authorization decision is actually reading the caller's real assigned role from
            # the database, not just coincidentally matching a hardcoded default.
            print("\nTest 4: Verifying a SuperAdmin-role user passes the same RBAC check...")
            async with SessionLocal() as session:
                super_admin_role = (await session.execute(select(Role).where(Role.name == "SuperAdmin"))).scalar_one()
                admin_user = User(
                    organization_id=test_org_id,
                    email=admin_email,
                    full_name="Admin Role User",
                    hashed_password=get_password_hash(password)
                )
                admin_user.roles.append(super_admin_role)
                session.add(admin_user)
                await session.commit()
                await session.refresh(admin_user)
                admin_user_id = admin_user.id

            res = await client.post("/api/v1/auth/login", json={"email": admin_email, "password": password})
            assert res.status_code == 200, f"Login failed: {res.text}"
            admin_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

            res = await client.post(
                "/api/v1/tools/execute",
                json={"tool_name": "delete_repository", "parameters": {}},
                headers=admin_headers
            )
            # delete_repository requires human approval regardless of role, so a SuperAdmin who
            # passes the RBAC check lands on WAITING_APPROVAL (200), not PERMISSION_DENIED (403) —
            # the opposite outcome of Test 3 for the identical tool call.
            assert res.status_code == 200, f"Expected SuperAdmin to pass RBAC (waiting_approval), got {res.status_code}: {res.text}"
            assert res.json()["status"] == "waiting_approval"
            print("SUCCESS: SuperAdmin-role user passed the RBAC check where the Developer was denied.")

        finally:
            print("\nCleaning up role assignment test database entries...")
            async with SessionLocal() as session:
                for uid in [u for u in [admin_user_id] if u]:
                    result = await session.execute(select(User).where(User.id == uid))
                    u = result.scalar_one_or_none()
                    if u:
                        await session.delete(u)
                if test_org_id:
                    result = await session.execute(select(Organization).where(Organization.id == test_org_id))
                    db_org = result.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Role Assignment & RBAC Differentiation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_role_assignment_flow())
