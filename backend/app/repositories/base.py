from typing import Any, Generic, List, Optional, Type, TypeVar
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base_class import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """Generic Base Repository mapping standard CRUD methods."""
        self.model = model
        self.session = session

    async def get(self, id: Any) -> Optional[ModelType]:
        """Fetch a single record by its ID."""
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_multi(self, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Fetch multiple records with offset and limit pagination."""
        result = await self.session.execute(select(self.model).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def create(self, obj_in: ModelType) -> ModelType:
        """Insert a new model instance into the database."""
        self.session.add(obj_in)
        await self.session.flush()
        return obj_in

    async def update(self, db_obj: ModelType, obj_in: Any) -> ModelType:
        """Update fields of an existing model instance using dict or Pydantic schemas."""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        for field in update_data:
            if hasattr(db_obj, field):
                setattr(db_obj, field, update_data[field])
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj

    async def remove(self, id: Any) -> Optional[ModelType]:
        """Delete a record by its ID."""
        obj = await self.get(id)
        if obj:
            await self.session.delete(obj)
            await self.session.flush()
        return obj
