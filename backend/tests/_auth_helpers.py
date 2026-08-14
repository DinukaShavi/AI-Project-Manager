import uuid
from httpx import AsyncClient


async def create_authenticated_headers(client: AsyncClient, organization_id, email: str = None, password: str = "TestPass123!") -> dict:
    """Register a user under organization_id, log in via the real /auth endpoints, and
    return an {"Authorization": "Bearer <access_token>"} header dict for use in test
    HTTP requests against endpoints protected by get_current_user."""
    email = email or f"test-{uuid.uuid4().hex[:10]}@example.com"

    res = await client.post(
        "/api/v1/users/register",
        json={
            "email": email,
            "full_name": "Test User",
            "organization_id": str(organization_id),
            "password": password
        }
    )
    assert res.status_code == 201, f"Test user registration failed: {res.text}"

    res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password}
    )
    assert res.status_code == 200, f"Test user login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
