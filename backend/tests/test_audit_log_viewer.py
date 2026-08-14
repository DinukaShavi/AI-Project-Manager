import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User, Role
from app.db.session import SessionLocal
from app.core.security import get_password_hash

async def test_audit_log_viewer_flow():
    print("Initializing Audit Logs Viewer validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    admin_user_id = None
    other_org_admin_id = None
    password = "ViewerPass123!"
    dev_email = f"viewer-dev-{suffix}@example.com"
    admin_email = f"viewer-admin-{suffix}@example.com"
    other_org_admin_email = f"viewer-otherorg-admin-{suffix}@example.com"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Viewer Org A {suffix}", domain=f"viewer-a-{suffix}.com")
                org_b = Organization(name=f"Viewer Org B {suffix}", domain=f"viewer-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.flush()
                org_a_id = org_a.id
                org_b_id = org_b.id
                await session.commit()
            print(f"Test Organizations created. A={org_a_id} B={org_b_id}")

            # 1. A default 'Developer'-role user (via normal registration) is generating audit
            # activity, but must NOT be able to view the audit log.
            print("\nTest 1: Verifying a Developer-role user is denied GET /audit-logs (403)...")
            res = await client.post(
                "/api/v1/users/register",
                json={"email": dev_email, "full_name": "Viewer Dev", "organization_id": str(org_a_id), "password": password}
            )
            assert res.status_code == 201, f"Registration failed: {res.text}"

            res = await client.post("/api/v1/auth/login", json={"email": dev_email, "password": password})
            assert res.status_code == 200
            dev_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

            # This login itself just wrote at least one audit_logs row (auth:register, auth:login_success)
            res = await client.get("/api/v1/audit-logs", headers=dev_headers)
            assert res.status_code == 403, f"Expected Developer role to be denied, got {res.status_code}: {res.text}"
            print("SUCCESS: Developer-role user correctly denied audit log access (403).")

            # 2. An OrgAdmin-role user (assigned directly, mirroring test_role_assignment.py's
            # pattern since there's no self-serve elevation endpoint yet) CAN view the log and
            # sees the Developer's own registration/login activity from the same org.
            print("\nTest 2: Verifying an OrgAdmin-role user can list the org's audit log...")
            async with SessionLocal() as session:
                org_admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                admin_user = User(
                    organization_id=org_a_id,
                    email=admin_email,
                    full_name="Viewer Admin",
                    hashed_password=get_password_hash(password)
                )
                admin_user.roles.append(org_admin_role)
                session.add(admin_user)
                await session.commit()
                await session.refresh(admin_user)
                admin_user_id = admin_user.id

            res = await client.post("/api/v1/auth/login", json={"email": admin_email, "password": password})
            assert res.status_code == 200
            admin_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

            res = await client.get("/api/v1/audit-logs", headers=admin_headers)
            assert res.status_code == 200, f"Expected OrgAdmin to view the audit log, got {res.status_code}: {res.text}"
            list_json = res.json()
            assert list_json["total"] >= 1
            assert any(e["action"] == "auth:register" and e["user_email"] == dev_email for e in list_json["entries"]), \
                "Expected the Developer's registration event to be visible to the OrgAdmin"
            print(f"SUCCESS: OrgAdmin viewed {list_json['total']} audit entries including the Developer's registration.")

            # 3. Filtering by action must narrow the result set correctly.
            print("\nTest 3: Verifying the 'action' filter narrows results...")
            res = await client.get("/api/v1/audit-logs?action=auth:register", headers=admin_headers)
            assert res.status_code == 200
            filtered = res.json()
            assert filtered["total"] >= 1
            assert all(e["action"] == "auth:register" for e in filtered["entries"])
            print("SUCCESS: Action filter correctly narrowed results.")

            # 4. Cross-tenant isolation: an OrgAdmin from a DIFFERENT organization must not see
            # Org A's audit entries at all, even though they hold the same elevated role.
            print("\nTest 4: Verifying cross-tenant isolation on the audit log endpoint...")
            async with SessionLocal() as session:
                org_admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                other_admin = User(
                    organization_id=org_b_id,
                    email=other_org_admin_email,
                    full_name="Other Org Admin",
                    hashed_password=get_password_hash(password)
                )
                other_admin.roles.append(org_admin_role)
                session.add(other_admin)
                await session.commit()
                await session.refresh(other_admin)
                other_org_admin_id = other_admin.id

            res = await client.post("/api/v1/auth/login", json={"email": other_org_admin_email, "password": password})
            assert res.status_code == 200
            other_admin_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

            res = await client.get("/api/v1/audit-logs", headers=other_admin_headers)
            assert res.status_code == 200
            other_org_json = res.json()
            assert all(e["user_email"] != dev_email for e in other_org_json["entries"]), \
                "Org B's admin must not see Org A's audit entries (tenant isolation violation)"
            print("SUCCESS: Org B's admin cannot see Org A's audit entries.")

        finally:
            print("\nCleaning up audit log viewer test database entries...")
            async with SessionLocal() as session:
                for uid in [u for u in [admin_user_id, other_org_admin_id] if u]:
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

    print("\nAll Audit Logs Viewer tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_audit_log_viewer_flow())
