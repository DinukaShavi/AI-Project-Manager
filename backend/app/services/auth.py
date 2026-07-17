from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.services.user import UserService
from app.models.tenant import User

class AuthService:
    def __init__(self, session: AsyncSession):
        """Auth Service managing authentication operations and token issuance."""
        self.user_service = UserService(session)

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by checking email and verifying password hash."""
        user = await self.user_service.get_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def login(self, email: str, password: str) -> Optional[Tuple[str, str]]:
        """Log in a user, returning (access_token, refresh_token) or None if validation fails."""
        user = await self.authenticate_user(email, password)
        if not user:
            return None
        # Generate short-lived access and long-lived refresh tokens
        access = create_access_token(user.id)
        refresh = create_refresh_token(user.id)
        return access, refresh

    async def refresh_tokens(self, refresh_token: str) -> Optional[Tuple[str, str]]:
        """Verify a refresh token and issue rotated access and refresh tokens."""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None
            
        user_id = payload.get("sub")
        if not user_id:
            return None
            
        user = await self.user_service.get_by_id(user_id)
        if not user or user.is_deleted:
            return None
            
        # Rotate access and refresh tokens
        new_access = create_access_token(user.id)
        new_refresh = create_refresh_token(user.id)
        return new_access, new_refresh
