"""Authentication models for FastAPI Users integration."""

from typing import Optional
from uuid import UUID

from fastapi_users import schemas
from fastapi_users.db import SQLAlchemyBaseUserTable
from pydantic import BaseModel, EmailStr

from server.database.models import User as UserModel


class UserRead(schemas.BaseUser[UUID]):
    """User read model for API responses."""

    email: EmailStr
    is_active: bool = True
    is_admin: bool = False
    auth_provider: str = 'local'
    auth_provider_user_id: Optional[str] = None


class UserCreate(schemas.BaseUserCreate):
    """User creation model."""

    email: EmailStr
    password: str
    is_admin: bool = False


class UserUpdate(schemas.BaseUserUpdate):
    """User update model."""

    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class UserTenantCreate(BaseModel):
    """User-tenant assignment creation model."""

    user_id: UUID
    tenant_id: UUID


class UserTenantRead(BaseModel):
    """User-tenant assignment read model."""

    id: UUID
    user_id: UUID
    tenant_id: UUID
    created_at: str
    updated_at: str


class User(UserModel, SQLAlchemyBaseUserTable[UUID]):
    """User model for FastAPI Users."""

    pass
