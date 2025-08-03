"""Authentication routes for user management."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.manager import fastapi_users, current_active_user, jwt_authentication
from server.auth.models import (
    User,
    UserCreate,
    UserRead,
    UserUpdate,
    UserTenantCreate,
    UserTenantRead,
)
from server.database import get_async_session
from server.services.user_service import UserService

router = APIRouter(prefix='/auth', tags=['authentication'])

# Include FastAPI Users routes
router.include_router(fastapi_users.get_auth_router(jwt_authentication), prefix='/jwt')
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))
router.include_router(fastapi_users.get_users_router(UserRead, UserUpdate))


@router.get('/me', response_model=UserRead)
async def get_current_user_info(current_user: User = Depends(current_active_user)):
    """Get current user information."""
    return current_user


@router.post('/users', response_model=UserRead)
async def create_user(
    user_create: UserCreate,
    current_user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new user (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only administrators can create users',
        )

    user_service = UserService(session)
    user = await user_service.create_user(
        email=user_create.email,
        hashed_password=user_create.password,  # Will be hashed by FastAPI Users
        is_admin=user_create.is_admin,
    )
    return user


@router.get('/users', response_model=List[UserRead])
async def get_users(
    current_user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get all users (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only administrators can view all users',
        )

    user_service = UserService(session)
    users = await user_service.get_users()
    return users


@router.put('/users/{user_id}', response_model=UserRead)
async def update_user(
    user_id: UUID,
    user_update: UserUpdate,
    current_user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a user (admin only or self)."""
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You can only update your own profile',
        )

    user_service = UserService(session)
    user = await user_service.update_user(user_id, user_update.dict(exclude_unset=True))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='User not found'
        )
    return user


@router.delete('/users/{user_id}')
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a user (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only administrators can delete users',
        )

    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Cannot delete your own account',
        )

    user_service = UserService(session)
    success = await user_service.delete_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='User not found'
        )
    return {'message': 'User deleted successfully'}


@router.post('/users/{user_id}/tenants', response_model=UserTenantRead)
async def assign_user_to_tenant(
    user_id: UUID,
    assignment: UserTenantCreate,
    current_user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Assign a user to a tenant (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only administrators can assign users to tenants',
        )

    user_service = UserService(session)
    user_tenant = await user_service.assign_user_to_tenant(
        user_id=user_id, tenant_id=assignment.tenant_id
    )
    return user_tenant


@router.get('/users/{user_id}/tenants', response_model=List[UserTenantRead])
async def get_user_tenants(
    user_id: UUID,
    current_user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get user's tenant assignments (admin or self)."""
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You can only view your own tenant assignments',
        )

    user_service = UserService(session)
    user_tenants = await user_service.get_user_tenants(user_id)
    return user_tenants


@router.delete('/users/{user_id}/tenants/{tenant_id}')
async def remove_user_from_tenant(
    user_id: UUID,
    tenant_id: UUID,
    current_user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Remove a user from a tenant (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only administrators can remove users from tenants',
        )

    user_service = UserService(session)
    success = await user_service.remove_user_from_tenant(user_id, tenant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User-tenant assignment not found',
        )
    return {'message': 'User removed from tenant successfully'}
