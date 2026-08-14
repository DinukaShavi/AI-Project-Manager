from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from typing import Any, List, Optional
from uuid import UUID

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    avatar_url: Optional[str] = None

class UserCreate(UserBase):
    organization_id: UUID
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    password: Optional[str] = None

class UserRead(UserBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime
    roles: List[str] = []

    @field_validator("roles", mode="before")
    @classmethod
    def _role_names(cls, v: Any) -> List[str]:
        """Accept either ORM Role objects (from a User.roles relationship) or plain strings."""
        if v and hasattr(next(iter(v), None), "name"):
            return [r.name for r in v]
        return v or []

    # Pydantic v2 ORM mapping configuration
    model_config = ConfigDict(from_attributes=True)
