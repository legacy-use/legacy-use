"""
Tenant management routes for multi-tenancy support.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server.database import db
from server.models.tenant import Tenant, TenantCreate, TenantUpdate, TenantAPIKey
from server.utils.auth import get_current_tenant
from server.database.models import TenantModel


router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("/", response_model=Tenant, status_code=status.HTTP_201_CREATED)
async def create_tenant(tenant_data: TenantCreate):
    """
    Create a new tenant with a generated API key.
    This endpoint should be protected in production (e.g., admin only).
    """
    try:
        # Check if subdomain already exists
        existing_tenants = db.list_tenants(include_inactive=True)
        for existing in existing_tenants:
            if existing['subdomain'] == tenant_data.subdomain:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Subdomain already exists"
                )
        
        # Create tenant
        tenant = db.create_tenant({
            'name': tenant_data.name,
            'subdomain': tenant_data.subdomain
        })
        
        return tenant
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create tenant: {str(e)}"
        )


@router.get("/", response_model=List[Tenant])
async def list_tenants(include_inactive: bool = False):
    """
    List all tenants.
    This endpoint should be protected in production (e.g., admin only).
    """
    tenants = db.list_tenants(include_inactive=include_inactive)
    return tenants


@router.get("/current", response_model=Tenant)
async def get_current_tenant_info(current_tenant: TenantModel = Depends(get_current_tenant)):
    """Get information about the current tenant based on API key."""
    return db._to_dict(current_tenant)


@router.get("/{tenant_id}", response_model=Tenant)
async def get_tenant(tenant_id: UUID):
    """
    Get a specific tenant by ID.
    This endpoint should be protected in production (e.g., admin only).
    """
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    return tenant


@router.put("/{tenant_id}", response_model=Tenant)
async def update_tenant(tenant_id: UUID, tenant_data: TenantUpdate):
    """
    Update a tenant.
    This endpoint should be protected in production (e.g., admin only).
    """
    tenant = db.update_tenant(tenant_id, tenant_data.dict(exclude_unset=True))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    return tenant


@router.post("/{tenant_id}/regenerate-api-key", response_model=TenantAPIKey)
async def regenerate_api_key(tenant_id: UUID):
    """
    Regenerate API key for a tenant.
    This endpoint should be protected in production (e.g., admin only).
    WARNING: This will invalidate the current API key!
    """
    tenant = db.regenerate_tenant_api_key(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    return TenantAPIKey(
        tenant_id=tenant['id'],
        api_key=tenant['api_key']  # This is only returned once
    )


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_tenant(tenant_id: UUID):
    """
    Deactivate a tenant (soft delete).
    This endpoint should be protected in production (e.g., admin only).
    """
    tenant = db.update_tenant(tenant_id, {'status': 'inactive'})
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )