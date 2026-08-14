from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import SessionLocal
from app.core.security import decode_token
from app.services.user import UserService
from app.models.tenant import User

# OAuth2 Password Bearer points to the login route for Swagger UI integration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding database async sessions."""
    async with SessionLocal() as session:
        yield session

async def resolve_user_from_access_token(db: AsyncSession, token: str) -> User | None:
    """Core access-token verification shared by every entry point that authenticates a
    caller from a raw JWT string -- HTTP's get_current_user (Authorization header) and
    the WebSocket endpoint (?token= query param, per api_contract.md section 17). Returns
    None rather than raising so each caller can respond with the transport-appropriate
    rejection (HTTP 401 vs a WebSocket close code)."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user_service = UserService(db)
    user = await user_service.get_by_id_with_roles(user_id)
    if not user or user.is_deleted:
        return None

    from app.db.session import set_tenant_session_context
    await set_tenant_session_context(db, user.organization_id)

    return user

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """Dependency verifying access tokens and injecting the active User instance."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = await resolve_user_from_access_token(db, token)
    if not user:
        raise credentials_exception
    return user
