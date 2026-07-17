from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import User
from app.schemas.user import UserCreate, UserUpdate
from app.repositories.user import UserRepository
from app.core.security import get_password_hash

class UserService:
    def __init__(self, session: AsyncSession):
        """User Service handling user-related business logic."""
        self.repository = UserRepository(session)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by their email address."""
        return await self.repository.get_by_email(email)

    async def get_by_id(self, user_id: Any) -> Optional[User]:
        """Fetch a user by their UUID."""
        return await self.repository.get(user_id)

    async def create_user(self, user_in: UserCreate) -> User:
        """Create a new user, hashing their password before saving."""
        existing_user = await self.get_by_email(user_in.email)
        if existing_user:
            raise ValueError(f"User with email {user_in.email} already exists.")
            
        hashed = get_password_hash(user_in.password)
        db_user = User(
            organization_id=user_in.organization_id,
            email=user_in.email,
            full_name=user_in.full_name,
            hashed_password=hashed,
            avatar_url=user_in.avatar_url
        )
        return await self.repository.create(db_user)

    async def update_user(self, db_user: User, user_in: UserUpdate) -> User:
        """Update user profile details and handle password updates."""
        update_dict = user_in.model_dump(exclude_unset=True)
        if "password" in update_dict and update_dict["password"]:
            update_dict["hashed_password"] = get_password_hash(update_dict.pop("password"))
        elif "password" in update_dict:
            update_dict.pop("password")
        return await self.repository.update(db_user, update_dict)
