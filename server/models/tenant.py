"""
Tenant models for multi-tenancy support.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TenantStatus(str, Enum):
    """Tenant status enum."""
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    SUSPENDED = 'suspended'


class Tenant(BaseModel):
    """Tenant model for API responses."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    subdomain: str
    schema_name: str
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    api_key_hash: str  # Hashed API key for security
    
    # Optional settings
    settings: dict = Field(default_factory=dict)


class TenantCreate(BaseModel):
    """Tenant creation model."""
    name: str
    subdomain: str
    # API key will be generated automatically


class TenantUpdate(BaseModel):
    """Tenant update model."""
    name: Optional[str] = None
    status: Optional[TenantStatus] = None
    settings: Optional[dict] = None


class TenantAPIKey(BaseModel):
    """Model for API key operations."""
    tenant_id: UUID
    api_key: str  # This will be the plain text key (only returned once)
    expires_at: Optional[datetime] = None