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

from server.database import db
from server.utils.auth import require_api_key
from server.utils.job_execution import (
    job_processor_task,
    job_queue,
    job_queue_lock,
    process_job_queue,
    running_job_tasks,
)

# Set up logging
logger = logging.getLogger(__name__)

# Create router
diagnostics_router = APIRouter(tags=['Diagnostics'])


@diagnostics_router.get('/diagnostics/queue')
async def diagnose_job_queue(_: str = require_api_key):
    """Get diagnostic information about the job queue and running jobs.

    This is a temporary endpoint to help diagnose issues with the job processing system.
    It provides insights into why jobs might be stuck in the QUEUED state.
    """
    # Gather diagnostic information
    diagnostics = {
        'timestamp': datetime.now().isoformat(),
        'queue_size': 0,
        'is_processor_running': job_processor_task is not None
        and not job_processor_task.done(),
        'running_jobs': {},
        'queued_jobs': [],
        'available_sessions': [],
        'session_states_count': {},
        'processor_task_status': 'Not initialized',
    }

    # Get processor task status
    if job_processor_task is not None:
        if job_processor_task.done():
            try:
                # Check if the task raised an exception
                exception = job_processor_task.exception()
                if exception:
                    diagnostics['processor_task_status'] = (
                        f'Failed with exception: {str(exception)}'
                    )
                    diagnostics['processor_task_traceback'] = ''.join(
                        traceback.format_exception(
                            type(exception), exception, exception.__traceback__
                        )
                    )
                else:
                    diagnostics['processor_task_status'] = 'Completed normally'
            except asyncio.InvalidStateError:
                diagnostics['processor_task_status'] = 'Task not done or cancelled'
        else:
            diagnostics['processor_task_status'] = 'Running'

    # Get queue information
    async with job_queue_lock:
        diagnostics['queue_size'] = len(job_queue)
        # Get details about queued jobs
        for job in job_queue:
            job_info = {
                'id': str(job.id),
                'api_name': job.api_name,
                'target_id': str(job.target_id),
                'status': job.status,
                'session_id': str(job.session_id) if job.session_id else None,
                'created_at': job.created_at.isoformat() if job.created_at else None,
            }
            diagnostics['queued_jobs'].append(job_info)

    # Get running jobs information
    for job_id, task in running_job_tasks.items():
        job_dict = db.get_job(UUID(job_id))
        if job_dict:
            diagnostics['running_jobs'][job_id] = {
                'api_name': job_dict['api_name'],
                'status': job_dict['status'],
                'target_id': str(job_dict['target_id']),
                'session_id': str(job_dict['session_id'])
                if job_dict.get('session_id')
                else None,
                'task_done': task.done(),
                'task_cancelled': task.cancelled(),
                'created_at': job_dict['created_at'].isoformat()
                if job_dict.get('created_at')
                else None,
                'updated_at': job_dict['updated_at'].isoformat()
                if job_dict.get('updated_at')
                else None,
            }
            if task.done():
                try:
                    # Check if the task raised an exception
                    exception = task.exception()
                    if exception:
                        diagnostics['running_jobs'][job_id]['task_exception'] = str(
                            exception
                        )
                except asyncio.InvalidStateError:
                    diagnostics['running_jobs'][job_id]['task_exception'] = (
                        'Task not done or cancelled'
                    )

    # Get session information
    all_sessions = db.list_sessions(include_archived=False)
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
async def start_job_processor(_: str = require_api_key):
    """Manually start the job queue processor.

    This endpoint can be used to manually start the job queue processor if it's
    not running or has stopped due to an exception.
    """
    global job_processor_task
    processor_info = {
        'timestamp': datetime.now().isoformat(),
        'previous_state': 'Not initialized',
        'action_taken': 'None',
        'current_state': 'Not initialized',
    }

    # Check current state
    if job_processor_task is None:
        processor_info['previous_state'] = 'Not initialized'
    elif job_processor_task.done():
        try:
            exception = job_processor_task.exception()
            if exception:
                processor_info['previous_state'] = (
                    f'Failed with exception: {str(exception)}'
                )
            else:
                processor_info['previous_state'] = 'Completed normally'
        except asyncio.InvalidStateError:
            processor_info['previous_state'] = 'Task not done or cancelled'
    else:
        processor_info['previous_state'] = 'Running'
        processor_info['action_taken'] = 'None - processor already running'
        return processor_info

    # Start the processor
    try:
        job_processor_task = asyncio.create_task(process_job_queue())
        processor_info['action_taken'] = 'Started new job processor task'
        processor_info['current_state'] = 'Running'

        # Add system log entry
        logger.info('Job processor manually started')
    except Exception as e:
        processor_info['action_taken'] = f'Failed to start processor: {str(e)}'
        processor_info['current_state'] = 'Failed'
        logger.error(f'Error manually starting job processor: {str(e)}')

    return processor_info


@diagnostics_router.get('/diagnostics/targets/{target_id}/sessions')
async def check_target_sessions(target_id: UUID, _: str = require_api_key):
    """Check if a target has available sessions.

    This can help diagnose why jobs for a specific target might be stuck in the QUEUED state.
    For jobs to run, there needs to be at least one session in the "ready" state.
    """
    # Check if target exists
    target = db.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail='Target not found')

    # Get all sessions for this target
    target_sessions = db.list_target_sessions(target_id, include_archived=False)

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
