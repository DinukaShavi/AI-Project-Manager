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
from app.models.tenant import Organization, User
from app.db.session import SessionLocal

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
            print("SUCCESS: Token rotation succeeded.")

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
