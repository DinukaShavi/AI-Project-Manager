from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import Role
from app.repositories.base import BaseRepository

class RoleRepository(BaseRepository[Role]):
    def __init__(self, session: AsyncSession):
        super().__init__(Role, session)

    async def get_by_name(self, name: str) -> Optional[Role]:
        """Fetch a role by its unique name (e.g. 'Developer', 'OrgAdmin')."""
        result = await self.session.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()
