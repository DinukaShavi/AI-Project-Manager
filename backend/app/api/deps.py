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
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise credentials_exception
        
    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception
        
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)
    if not user or user.is_deleted:
        raise credentials_exception
    
    from app.db.session import set_tenant_session_context
    await set_tenant_session_context(db, user.organization_id)
    
    return user
