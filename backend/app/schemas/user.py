from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
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

    # Pydantic v2 ORM mapping configuration
    model_config = ConfigDict(from_attributes=True)
