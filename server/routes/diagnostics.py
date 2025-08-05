"""
Diagnostic routes for the API Gateway.

These endpoints provide diagnostic information about the API Gateway,
particularly focused on job queue processing and session status.
They are intended for debugging and monitoring purposes.
"""

import asyncio
import logging
import traceback
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends

from server.utils.db_dependencies import get_tenant_db
from server.utils.tenant_utils import get_tenant_from_request
from server.utils.hatchet_job_execution import (
    running_job_tasks,
)
# Note: tenant_job_queues, tenant_processor_tasks, tenant_resources_lock 
# are no longer used with Hatchet - queue management is handled by Hatchet server

# Set up logging
logger = logging.getLogger(__name__)

# Create router
diagnostics_router = APIRouter(tags=['Diagnostics'])


@diagnostics_router.get('/diagnostics/queue')
async def diagnose_job_queue(
    db_tenant=Depends(get_tenant_db),
    tenant: dict = Depends(get_tenant_from_request),
):
    """Get diagnostic information about the job queue and running jobs for the current tenant.

    This is a temporary endpoint to help diagnose issues with the job processing system.
    It provides insights into why jobs might be stuck in the QUEUED state.
    """
    # Gather diagnostic information
    diagnostics = {
        'timestamp': datetime.now().isoformat(),
        'tenant_schema': tenant['schema'],
        'queue_size': 0,
        'is_processor_running': False,
        'running_jobs': {},
        'queued_jobs': [],
        'available_sessions': [],
        'session_states_count': {},
        'processor_task_status': 'Not initialized',
    }

    # Get processor task status for current tenant
    tenant_schema = tenant['schema']
    # With Hatchet, job processing is handled by external workers
    diagnostics['is_processor_running'] = True  # Assume Hatchet workers are running
    diagnostics['processor_task_status'] = 'Managed by Hatchet workers'
    
    # Queue information is now managed by Hatchet
    # We can show running jobs from our tracking
    diagnostics['queue_size'] = len([
        job_id for job_id, job_info in running_job_tasks.items() 
        if job_info.get('tenant_schema') == tenant_schema and job_info.get('status') == 'queued'
    ])
    
         # Get running jobs information (now tracked via Hatchet)
     for job_id, job_info in running_job_tasks.items():
         if job_info.get('tenant_schema') != tenant_schema:
             continue
             
         # Get job details from database
         try:
             job_dict = db_tenant.get_job(UUID(job_id))
             if job_dict:
                 diagnostics['running_jobs'][job_id] = {
                     'api_name': job_dict['api_name'],
                     'status': job_dict['status'],
                     'target_id': str(job_dict['target_id']),
                     'session_id': str(job_dict['session_id'])
                     if job_dict.get('session_id')
                     else None,
                     'workflow_run_id': job_info.get('workflow_run_id'),
                     'hatchet_status': job_info.get('status', 'unknown'),
                     'created_at': job_dict['created_at'].isoformat()
                     if job_dict.get('created_at')
                     else None,
                     'updated_at': job_dict['updated_at'].isoformat()
                     if job_dict.get('updated_at')
                     else None,
                 }
         except Exception as e:
             logger.error(f"Error getting job {job_id} details: {e}")
             diagnostics['running_jobs'][job_id] = {
                 'error': f'Failed to get job details: {str(e)}',
                 'workflow_run_id': job_info.get('workflow_run_id'),
                 'hatchet_status': job_info.get('status', 'unknown'),
             }

    # Get session information
    all_sessions = db_tenant.list_sessions(include_archived=False)
    # Count sessions by state
    for session in all_sessions:
        state = session.get('state', 'unknown')
        diagnostics['session_states_count'][state] = (
            diagnostics['session_states_count'].get(state, 0) + 1
        )
        # Only include ready sessions in the available list
        if state == 'ready':
            diagnostics['available_sessions'].append(
                {
                    'id': str(session['id']),
                    'target_id': str(session['target_id']),
                    'state': state,
                    'created_at': session['created_at'].isoformat()
                    if session.get('created_at')
                    else None,
                }
            )

    # Get system resource information if available
    try:
        import psutil

        diagnostics['system'] = {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
        }
    except ImportError:
        # psutil not available, skip system metrics
        diagnostics['system'] = 'psutil not available'

    return diagnostics


@diagnostics_router.post('/diagnostics/queue/start')
async def start_job_processor(
    db_tenant=Depends(get_tenant_db),
    tenant: dict = Depends(get_tenant_from_request),
):
    """Manually start the job queue processor for the current tenant.

    This endpoint can be used to manually start the job queue processor if it's
    not running or has stopped due to an exception.
    """
    from server.utils.hatchet_job_execution import start_job_processor_for_tenant

    tenant_schema = tenant['schema']
    processor_info = {
        'timestamp': datetime.now().isoformat(),
        'tenant_schema': tenant_schema,
        'previous_state': 'Not initialized',
        'action_taken': 'None',
        'current_state': 'Not initialized',
    }

    # With Hatchet, job processing is managed by external workers
    # This endpoint is now mainly informational
    processor_info['previous_state'] = 'Managed by Hatchet workers'
    processor_info['action_taken'] = 'No action needed - using Hatchet workers'
    processor_info['current_state'] = 'Managed by Hatchet workers'
    
    logger.info(f'Job processor status check for tenant {tenant_schema} - using Hatchet workers')
    return processor_info




@diagnostics_router.get('/diagnostics/targets/{target_id}/sessions')
async def check_target_sessions(target_id: UUID, db_tenant=Depends(get_tenant_db)):
    """Check if a target has available sessions.

    This can help diagnose why jobs for a specific target might be stuck in the QUEUED state.
    For jobs to run, there needs to be at least one session in the "ready" state.
    """
    # Check if target exists
    target = db_tenant.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail='Target not found')

    # Get all sessions for this target
    target_sessions = db_tenant.list_target_sessions(target_id, include_archived=False)

    # Prepare response
    result = {
        'target_id': str(target_id),
        'target_name': target.get('name', 'Unknown'),
        'target_type': target.get('target_type', 'Unknown'),
        'total_sessions': len(target_sessions),
        'ready_sessions': 0,
        'sessions_by_state': {},
        'has_available_sessions': False,
        'recommendations': [],
    }

    # Analyze sessions
    for session in target_sessions:
        state = session.get('state', 'unknown')
        result['sessions_by_state'][state] = (
            result['sessions_by_state'].get(state, 0) + 1
        )

        if state == 'ready':
            result['ready_sessions'] += 1
            result['has_available_sessions'] = True

    # Generate recommendations
    if result['total_sessions'] == 0:
        result['recommendations'].append(
            'No sessions exist for this target. Create a new session.'
        )
    elif result['ready_sessions'] == 0:
        result['recommendations'].append(
            'No ready sessions available. Check session states and restart any failed sessions or create new ones.'
        )
        # Check for specific states and provide more detailed recommendations
        if result['sessions_by_state'].get('creating', 0) > 0:
            result['recommendations'].append(
                'Some sessions are still being created. Wait for them to become ready.'
            )
        if result['sessions_by_state'].get('error', 0) > 0:
            result['recommendations'].append(
                'Some sessions are in error state. Check logs and fix any issues, then create new sessions.'
            )
        if (
            result['sessions_by_state'].get('destroyed', 0) > 0
            or result['sessions_by_state'].get('destroying', 0) > 0
        ):
            result['recommendations'].append(
                'Some sessions have been destroyed. Create new sessions.'
            )
    else:
        result['recommendations'].append(
            'Target has available sessions. Jobs should be processed normally.'
        )

    return result
