import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User, Role
from app.db.session import SessionLocal
from app.core.security import get_password_hash

async def test_organization_settings_flow():
    print("Initializing Organization Settings Console validation tests...")

    suffix = uuid.uuid4().hex[:6]
    password = "OrgSettingsPass123!"
    org_a_id = None
    org_b_id = None
    org_admin_id = None
    dev_id = None
    other_org_admin_id = None

    dev_email = f"orgset-dev-{suffix}@example.com"
    org_admin_email = f"orgset-admin-{suffix}@example.com"
    other_org_admin_email = f"orgset-otheradmin-{suffix}@example.com"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(
                    name=f"Settings Test Org {suffix}",
                    domain=f"settings-{suffix}.com",
                    allowed_email_domains=[f"settings-{suffix}.com"]
                )
                org_b = Organization(name=f"Settings Test Org B {suffix}", domain=f"settings-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id = org_a.id
                org_b_id = org_b.id

                org_admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                org_admin = User(organization_id=org_a_id, email=org_admin_email, full_name="Org Admin", hashed_password=get_password_hash(password))
                org_admin.roles.append(org_admin_role)
                other_admin = User(organization_id=org_b_id, email=other_org_admin_email, full_name="Other Org Admin", hashed_password=get_password_hash(password))
                other_admin.roles.append(org_admin_role)
                session.add_all([org_admin, other_admin])
                await session.commit()
                await session.refresh(org_admin)
                await session.refresh(other_admin)
                org_admin_id = org_admin.id
                other_org_admin_id = other_admin.id
            print(f"Test orgs and admins created. Org A={org_a_id} Org B={org_b_id}")

            res = await client.post(
                "/api/v1/users/register",
                json={"email": dev_email, "full_name": "Settings Dev", "organization_id": str(org_a_id), "password": password}
            )
            assert res.status_code == 201, f"Registration failed: {res.text}"
            dev_id = uuid.UUID(res.json()["id"])

            async def login(email: str) -> dict:
                res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
                assert res.status_code == 200, f"Login failed for {email}: {res.text}"
                return {"Authorization": f"Bearer {res.json()['access_token']}"}

            org_admin_headers = await login(org_admin_email)
            dev_headers = await login(dev_email)
            other_admin_headers = await login(other_org_admin_email)

            # 1. A Developer cannot view organization settings.
            print("\nTest 1: Verifying a Developer-role user is denied GET /organizations/settings (403)...")
            res = await client.get("/api/v1/organizations/settings", headers=dev_headers)
            assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
            print("SUCCESS: Developer correctly denied.")

            # 2. An OrgAdmin can view settings, matching docs/api_contract.md's response schema.
            print("\nTest 2: Verifying OrgAdmin can view org settings with the documented schema...")
            res = await client.get("/api/v1/organizations/settings", headers=org_admin_headers)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            settings_json = res.json()
            for field in ("organization_id", "name", "domain", "allowed_email_domains", "created_at"):
                assert field in settings_json, f"Missing documented field '{field}' in response: {settings_json}"
            assert settings_json["organization_id"] == str(org_a_id)
            assert settings_json["allowed_email_domains"] == [f"settings-{suffix}.com"]
            print("SUCCESS: Org settings response matches the documented api_contract.md schema.")

            # 3. An OrgAdmin can list members and sees the Developer with their default role.
            print("\nTest 3: Verifying OrgAdmin can list organization members with roles...")
            res = await client.get("/api/v1/organizations/members", headers=org_admin_headers)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            members_json = res.json()
            dev_member = next((m for m in members_json["members"] if m["email"] == dev_email), None)
            assert dev_member is not None, "Expected the registered Developer to appear in the members list"
            assert dev_member["roles"] == ["Developer"]
            print(f"SUCCESS: Members list returned {members_json['members_count']} members including the Developer's role.")

            # 4. Cross-tenant isolation: Org B's admin sees only Org B's org settings/members, never Org A's.
            print("\nTest 4: Verifying organization settings/members are tenant-isolated...")
            res = await client.get("/api/v1/organizations/settings", headers=other_admin_headers)
            assert res.status_code == 200
            assert res.json()["organization_id"] == str(org_b_id)

            res = await client.get("/api/v1/organizations/members", headers=other_admin_headers)
            assert res.status_code == 200
            assert all(m["email"] != dev_email for m in res.json()["members"]), \
                "Org B's admin must not see Org A's members (tenant isolation violation)"
            print("SUCCESS: Organization settings and members are correctly tenant-isolated.")

        finally:
            print("\nCleaning up organization settings test database entries...")
            async with SessionLocal() as session:
                for uid in [u for u in [dev_id, org_admin_id, other_org_admin_id] if u]:
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

    print("\nAll Organization Settings Console tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_organization_settings_flow())
