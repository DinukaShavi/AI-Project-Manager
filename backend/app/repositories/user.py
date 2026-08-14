from typing import List, Optional
from uuid import UUID
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

    async def get_by_id_with_roles(self, user_id) -> Optional[User]:
        """Fetch a user by ID, eager loading their associated roles (avoids a lazy-load
        MissingGreenlet error under AsyncSession if callers need .roles afterward)."""
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_organization(self, organization_id: UUID) -> List[User]:
        """List all (non-deleted) users in an organization, eager loading their roles."""
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.organization_id == organization_id, User.deleted_at.is_(None))
            .order_by(User.email)
        )
        return list(result.scalars().all())
