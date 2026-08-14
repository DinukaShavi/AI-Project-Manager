from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import Organization
from app.repositories.base import BaseRepository

class OrganizationRepository(BaseRepository[Organization]):
    def __init__(self, session: AsyncSession):
        super().__init__(Organization, session)
