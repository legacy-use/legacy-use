"""
Target management routes.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Depends

from server.models.base import Target, TargetCreate, TargetUpdate
from server.settings import settings
from server.utils.db_dependencies import get_tenant_db
from server.utils.telemetry import (
    capture_target_created,
    capture_target_deleted,
    capture_target_updated,
)

# Create router
target_router = APIRouter(prefix='/targets', tags=['Target Management'])


@target_router.get('/', response_model=List[Target])
async def list_targets(
    include_archived: bool = False, db_tenant=Depends(get_tenant_db)
):
    """List all available targets."""
    targets = db_tenant.list_targets(include_archived)

    # Add queue status and blocking jobs information to each target
    for target in targets:
        blocking_info = db_tenant.is_target_queue_paused(target['id'])
        target['queue_status'] = 'paused' if blocking_info['is_paused'] else 'running'
        target['blocking_jobs'] = blocking_info['blocking_jobs']
        target['has_blocking_jobs'] = blocking_info['is_paused']
        target['blocking_jobs_count'] = blocking_info['blocking_jobs_count']
        # Ensure new fields exist in response (defaulting if missing)
        if 'rdp_params' not in target:
            target['rdp_params'] = None
        if 'rdp_override_defaults' not in target:
            target['rdp_override_defaults'] = False

        # Add active session status to each target
        target['has_active_session'] = db_tenant.has_active_session_for_target(
            target['id']
        )['has_active_session']
        target['has_initializing_session'] = (
            db_tenant.has_initializing_session_for_target(target['id'])
        )

    return targets


@target_router.post('/', response_model=Target)
async def create_target(
    target: TargetCreate, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Create a new target."""
    # Convert the Pydantic model to a dictionary and pass it to the database service
    result = db_tenant.create_target(target.dict())
    capture_target_created(request, result.get('id', ''), target)
    return result


@target_router.get('/{target_id}', response_model=Target)
async def get_target(target_id: UUID, db_tenant=Depends(get_tenant_db)):
    """Get details of a specific target."""
    target = db_tenant.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail='Target not found')

    # Add queue status and blocking jobs information
    blocking_info = db_tenant.is_target_queue_paused(target_id)
    target['queue_status'] = 'paused' if blocking_info['is_paused'] else 'running'
    target['blocking_jobs'] = blocking_info['blocking_jobs']
    target['has_blocking_jobs'] = blocking_info['is_paused']
    target['blocking_jobs_count'] = blocking_info['blocking_jobs_count']

    return target


@target_router.put('/{target_id}', response_model=Target)
async def update_target(
    target_id: UUID,
    target: TargetUpdate,
    request: Request,
    db_tenant=Depends(get_tenant_db),
):
    """Update a target's configuration."""
    if not db_tenant.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')

    updated_target = db_tenant.update_target(target_id, target.dict(exclude_unset=True))

    # Add queue status and blocking jobs information
    blocking_info = db_tenant.is_target_queue_paused(target_id)
    updated_target['queue_status'] = (
        'paused' if blocking_info['is_paused'] else 'running'
    )
    updated_target['blocking_jobs'] = blocking_info['blocking_jobs']
    updated_target['has_blocking_jobs'] = blocking_info['is_paused']
    updated_target['blocking_jobs_count'] = blocking_info['blocking_jobs_count']
    if 'rdp_params' not in updated_target:
        updated_target['rdp_params'] = None
    if 'rdp_override_defaults' not in updated_target:
        updated_target['rdp_override_defaults'] = False

    capture_target_updated(request, target_id, target)

    return updated_target


@target_router.delete('/{target_id}')
async def delete_target(
    target_id: UUID, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Archive a target (soft delete)."""
    if not db_tenant.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')
    db_tenant.delete_target(target_id)
    capture_target_deleted(request, target_id, False)
    return {'message': 'Target archived'}


@target_router.delete(
    '/{target_id}/hard',
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
async def hard_delete_target(
    target_id: UUID, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Permanently delete a target (hard delete)."""
    if not db_tenant.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')
    db_tenant.hard_delete_target(target_id)
    capture_target_deleted(request, target_id, True)
    return {'message': 'Target permanently deleted'}


@target_router.post('/{target_id}/unarchive')
async def unarchive_target(
    target_id: UUID, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Unarchive a target."""
    if not db_tenant.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')

    success = db_tenant.unarchive_target(target_id)
    if not success:
        raise HTTPException(status_code=404, detail='Target not found')

    return {'message': 'Target unarchived successfully'}
