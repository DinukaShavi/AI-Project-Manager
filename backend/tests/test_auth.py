import asyncio
from datetime import datetime, timezone
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import app.db.base # Register models
from app.main import app
from app.core.config import settings
from app.core.security import verify_password, get_password_hash
from app.models.tenant import Organization, User, Role
from app.models.audit import AuditLog
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers

async def test_auth_and_user_flow():
    print("Initializing Authentication and User API integration tests...")
    
    # 1. Test Password Hashing
    print("\nTest 1: Verifying password hashing utilities...")
    pw = "supersecret123"
    hashed = get_password_hash(pw)
    assert verify_password(pw, hashed)
    assert not verify_password("wrong_password", hashed)
    print("SUCCESS: Hashing utilities working correctly.")

    # Generate unique suffix for test isolation
    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    test_user_id = None

    # We use AsyncClient to execute all API calls on the same event loop
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # Create test records directly in the DB
            async with SessionLocal() as session:
                print("\nInserting test tenant database entries...")
                org = Organization(name=f"Auth Test Org {suffix}", domain=f"authtest-{suffix}.com")
                session.add(org)
                await session.flush()
                test_org_id = org.id

                user = User(
                    organization_id=org.id,
                    email=f"bob-{suffix}@example.com",
                    full_name="Bob Jones",
                    hashed_password=get_password_hash("password123")
                )
                session.add(user)
                await session.commit()
                test_user_id = user.id
                print(f"Test entries created. User email: {user.email}")

            # 2. Test POST /api/v1/auth/login
            print("\nTest 2: Requesting POST /api/v1/auth/login...")
            login_data = {
                "email": f"bob-{suffix}@example.com",
                "password": "password123"
            }
            response = await client.post("/api/v1/auth/login", json=login_data)
            assert response.status_code == 200, f"Login failed: {response.text}"
            tokens = response.json()
            assert "access_token" in tokens
            assert "refresh_token" in tokens
            assert tokens["token_type"] == "bearer"
            access_token = tokens["access_token"]
            refresh_token = tokens["refresh_token"]
            print("SUCCESS: Login returned JWT token pair.")

            # 3. Test GET /api/v1/users/me (unauthenticated - should fail)
            print("\nTest 3: Requesting GET /api/v1/users/me without token...")
            response = await client.get("/api/v1/users/me")
            assert response.status_code == 401
            print("SUCCESS: Unauthorized access blocked.")

            # 4. Test GET /api/v1/users/me (authenticated - should succeed)
            print("\nTest 4: Requesting GET /api/v1/users/me with access token...")
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await client.get("/api/v1/users/me", headers=headers)
            assert response.status_code == 200, f"Authenticated me failed: {response.text}"
            profile = response.json()
            assert profile["email"] == f"bob-{suffix}@example.com"
            assert profile["full_name"] == "Bob Jones"
            assert profile["id"] == str(test_user_id)
            print("SUCCESS: Authenticated profile fetched successfully.")

            # 5. Test POST /api/v1/auth/refresh
            print("\nTest 5: Requesting POST /api/v1/auth/refresh...")
            refresh_data = {
                "refresh_token": refresh_token
            }
            response = await client.post("/api/v1/auth/refresh", json=refresh_data)
            assert response.status_code == 200, f"Token refresh failed: {response.text}"
            new_tokens = response.json()
            assert "access_token" in new_tokens
            assert "refresh_token" in new_tokens
            rotated_refresh_token = new_tokens["refresh_token"]
            print("SUCCESS: Token rotation succeeded.")

            # 6. A successful refresh must create an 'auth:token_refresh_success' audit
            # entry, correctly attributed to the real user/organization, with no
            # credential material in its details.
            print("\nTest 6: Verifying a successful refresh creates the expected audit entry...")
            async with SessionLocal() as session:
                res_db = await session.execute(
                    select(AuditLog).where(AuditLog.organization_id == test_org_id, AuditLog.action == "auth:token_refresh_success")
                )
                success_logs = res_db.scalars().all()
            assert len(success_logs) == 1
            assert success_logs[0].user_id == test_user_id
            for secret in [access_token, refresh_token, rotated_refresh_token]:
                assert secret not in str(success_logs[0].details)
            print("SUCCESS: 'auth:token_refresh_success' audit entry recorded with no leaked token material.")

            # 7. A refresh attempt with a syntactically-invalid/garbage token has no
            # verifiable identity at all -- it must be rejected (401) but must NOT create
            # any audit row, since AuditService.log() requires a real organization_id that
            # cannot be safely determined here (never fabricate one).
            print("\nTest 7: Verifying an unattributable invalid-token rejection creates NO audit row...")
            async with SessionLocal() as session:
                before_count = len((await session.execute(
                    select(AuditLog).where(AuditLog.organization_id == test_org_id)
                )).scalars().all())
            response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-jwt-at-all"})
            assert response.status_code == 401
            async with SessionLocal() as session:
                after_count = len((await session.execute(
                    select(AuditLog).where(AuditLog.organization_id == test_org_id)
                )).scalars().all())
            assert after_count == before_count, "An unattributable invalid-token rejection must not create an audit row"
            print("SUCCESS: Invalid/unattributable token rejection correctly created no audit row.")

            # 8. A refresh attempt for a user that has since been soft-deleted DOES have a
            # safely-known organization (the token's signature is valid and the user row
            # was found) -- this rejection case must be audited.
            print("\nTest 8: Verifying a refresh for a soft-deleted user creates 'auth:token_refresh_failed'...")
            async with SessionLocal() as session:
                db_user = await session.get(User, test_user_id)
                db_user.deleted_at = datetime.now(timezone.utc)
                await session.commit()

            response = await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated_refresh_token})
            assert response.status_code == 401, f"Expected 401 for a soft-deleted user, got {response.status_code}"

            async with SessionLocal() as session:
                res_db = await session.execute(
                    select(AuditLog).where(AuditLog.organization_id == test_org_id, AuditLog.action == "auth:token_refresh_failed")
                )
                failed_logs = res_db.scalars().all()
            assert len(failed_logs) == 1
            assert failed_logs[0].user_id == test_user_id
            assert failed_logs[0].details.get("reason") == "user_deleted"
            for secret in [access_token, refresh_token, rotated_refresh_token]:
                assert secret not in str(failed_logs[0].details)
            print("SUCCESS: 'auth:token_refresh_failed' audit entry recorded for the soft-deleted-user rejection, with no leaked token material.")

            # 9. Cross-tenant isolation: an OrgAdmin from a different organization cannot
            # see this organization's refresh audit trail via the real audit-log endpoint.
            print("\nTest 9: Verifying cross-tenant isolation of the refresh audit trail...")
            other_org_suffix = uuid.uuid4().hex[:6]
            async with SessionLocal() as session:
                other_org = Organization(name=f"Auth Refresh Other Org {other_org_suffix}", domain=f"authrefresh-other-{other_org_suffix}.com")
                session.add(other_org)
                await session.flush()
                other_org_id = other_org.id

                org_admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                own_org_admin_role = org_admin_role
                own_admin = User(
                    organization_id=test_org_id, email=f"refresh-admin-{suffix}@example.com",
                    full_name="Refresh Admin", hashed_password=get_password_hash("AdminPass123!")
                )
                own_admin.roles.append(own_org_admin_role)
                session.add(own_admin)
                await session.commit()
                own_admin_id = own_admin.id

            login_res = await client.post("/api/v1/auth/login", json={"email": f"refresh-admin-{suffix}@example.com", "password": "AdminPass123!"})
            assert login_res.status_code == 200, login_res.text
            own_admin_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
            other_admin_headers = await create_authenticated_headers(client, other_org_id)
            try:
                res = await client.get("/api/v1/audit-logs", headers=other_admin_headers)
                assert res.status_code in (200, 403)
                if res.status_code == 200:
                    other_actions = {e["action"] for e in res.json()["entries"]}
                    assert "auth:token_refresh_success" not in other_actions
                    assert "auth:token_refresh_failed" not in other_actions

                res = await client.get("/api/v1/audit-logs", headers=own_admin_headers)
                assert res.status_code == 200, res.text
                own_actions = {e["action"] for e in res.json()["entries"]}
                assert "auth:token_refresh_success" in own_actions
                assert "auth:token_refresh_failed" in own_actions
                print("SUCCESS: Refresh audit entries are correctly tenant-isolated; the owning org's admin sees both.")
            finally:
                async with SessionLocal() as session:
                    res_u = await session.execute(select(User).where(User.organization_id == other_org_id))
                    for u in res_u.scalars().all():
                        await session.delete(u)
                    await session.commit()
                    res_o = await session.execute(select(Organization).where(Organization.id == other_org_id))
                    db_other_org = res_o.scalar_one_or_none()
                    if db_other_org:
                        await session.delete(db_other_org)
                    await session.commit()

        finally:
            # Cleanup test records
            if test_user_id or test_org_id:
                print("\nCleaning up test database entries...")
                async with SessionLocal() as session:
                    if test_user_id:
                        res = await session.execute(select(User).where(User.id == test_user_id))
                        db_user = res.scalar_one_or_none()
                        if db_user:
                            await session.delete(db_user)
                    if test_org_id:
                        res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                        db_org = res.scalar_one_or_none()
                        if db_org:
                            await session.delete(db_org)
                    await session.commit()
                print("Cleanup completed.")

    print("\nAll Auth and User endpoint tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_auth_and_user_flow())
