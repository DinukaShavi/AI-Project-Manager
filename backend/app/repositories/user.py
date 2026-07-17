from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import User
from app.repositories.base import BaseRepository

class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by email, eager loading their associated roles."""
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == email)
        )
        return result.scalar_one_or_none()
