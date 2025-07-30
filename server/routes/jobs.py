"""
Job management routes.

This module provides endpoints for managing jobs in the API Gateway.

Jobs can be created, listed, and interrupted. Jobs are added
to the queue and the endpoint returns immediately.

Example:
    # Create a job and return immediately
    POST /targets/{target_id}/jobs/
    {
        "api_name": "example_api",
        "parameters": {"param1": "value1"},
    }

"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Request, Depends
from pydantic import BaseModel

from server.core import APIGatewayCore
from server.database.service import DatabaseService
from server.models.base import Job, JobCreate, JobStatus
from server.settings import settings
from server.utils.auth import require_api_key
from server.utils.job_execution import (
    add_job_log,
    enqueue_job,
    job_processor_task,
    job_queue,
    job_queue_initializer,
    job_queue_lock,
    process_next_job,
    running_job_tasks,
)
from server.utils.job_utils import compute_job_metrics
from server.utils.telemetry import (
    capture_job_canceled,
    capture_job_created,
    capture_job_interrupted,
    capture_job_resolved,
    capture_job_resumed,
)

# Set up logging
logger = logging.getLogger(__name__)

# Initialize core and database
core = APIGatewayCore()

# Create router
job_router = APIRouter(tags=['Job Management'])


class JobLogEntry(BaseModel):
    id: UUID
    job_id: UUID
    timestamp: datetime
    log_type: str
    content: Any


class HttpExchangeLog(BaseModel):
    id: UUID
    job_id: UUID
    timestamp: datetime
    log_type: str = 'http_exchange'
    content: Dict[str, Any]  # Contains structured request and response


class PaginatedJobsResponse(BaseModel):
    total_count: int
    jobs: List[Job]


# Initialize database
db = DatabaseService()

# Dictionary to store completion futures
completion_futures = {}


@job_router.get('/jobs/', response_model=PaginatedJobsResponse)
async def list_all_jobs(
    limit: int = 10,
    offset: int = 0,
    status: Optional[str] = None,
    target_id: Optional[UUID] = None,
    api_name: Optional[str] = None,
    _: str = require_api_key
):
    """List all jobs across all targets with pagination and filtering options."""
    # Build filters dict from parameters
    filters = {}
    if status:
        filters['status'] = status
    if target_id:
        filters['target_id'] = target_id
    if api_name:
        filters['api_name'] = api_name

    # Pass filters to database methods
    jobs_data = db.list_jobs(limit=limit, offset=offset, filters=filters)
    total_count = db.count_jobs(filters=filters)

    # Compute metrics for each job
    enriched_jobs = []
    for job_dict in jobs_data:
        # Convert dict to Job model if needed, or assume db returns dict compatible with Job model
        job_model = Job(**job_dict)
        http_exchanges = db.list_job_http_exchanges(job_model.id, use_trimmed=True)
        metrics = compute_job_metrics(job_dict, http_exchanges)
        job_model_dict = job_model.model_dump()  # Use model_dump() for Pydantic v2
        job_model_dict.update(metrics)
        enriched_jobs.append(
            Job(**job_model_dict)
        )  # Create a new Job instance with updated metrics

    return PaginatedJobsResponse(total_count=total_count, jobs=enriched_jobs)


@job_router.get('/targets/{target_id}/jobs/', response_model=List[Job])
async def list_target_jobs(target_id: UUID, limit: int = 10, offset: int = 0, _: str = require_api_key):
    """List all jobs for a specific target with pagination."""
    if not db.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')

    jobs_data = db.list_target_jobs(target_id, limit=limit, offset=offset)

    # Compute metrics for each job
    enriched_jobs = []
    for job_dict in jobs_data:
        job_model = Job(**job_dict)
        http_exchanges = db.list_job_http_exchanges(job_model.id, use_trimmed=True)
        metrics = compute_job_metrics(job_dict, http_exchanges)
        job_model_dict = job_model.model_dump()
        job_model_dict.update(metrics)
        enriched_jobs.append(Job(**job_model_dict))

    return enriched_jobs


@job_router.post('/targets/{target_id}/jobs/', response_model=Job)
async def create_job(target_id: UUID, job: JobCreate, request: Request, _: str = require_api_key):
    """Create a new job for a target.

    The endpoint will return immediately after adding the job to the queue.

    Note: Jobs have a token usage limit of 15,000 tokens (combined input and output).
    Jobs exceeding this limit will be automatically terminated.
    """
    # Check if target exists
    target = db.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail='Target not found')

    # Create job in database
    job_data = job.model_dump()  # Use model_dump() for Pydantic v2

    # Set target_id
    job_data['target_id'] = target_id

    # Try to get the API definition version ID
    try:
        # Load API definitions fresh from the database
        api_definitions = await core.load_api_definitions()

        # Check if the API definition exists
        api_def = api_definitions.get(job.api_name)
        if api_def and hasattr(api_def, 'version_id'):
            job_data['api_definition_version_id'] = api_def.version_id
        elif not api_def:
            logger.warning(
                f"API definition '{job.api_name}' not found during job creation."
            )

    except Exception as e:
        logger.error(
            f"Error getting API definition during job creation for '{job.api_name}': {str(e)}"
        )

    db_job_dict = db.create_job(job_data)

    # Create job object from the dictionary returned by the database
    job_obj = Job(**db_job_dict)

    # Use the new helper function to update status, add to queue, and ensure processor runs

    await enqueue_job(job_obj)

    capture_job_created(request, job_obj)

    return job_obj


@job_router.get('/targets/{target_id}/jobs/{job_id}', response_model=Job)
async def get_job(target_id: UUID, job_id: UUID, _: str = require_api_key):
    """Get details of a specific job."""
    # Check if target exists
    target_data = db.get_target(target_id)
    if not target_data:
        raise HTTPException(status_code=404, detail='Target not found')

    # Get job data (dictionary)
    job_dict = db.get_target_job(target_id, job_id)
    if not job_dict:
        raise HTTPException(status_code=404, detail='Job not found')

    # Create Job model instance
    job_model = Job(**job_dict)

    # Get HTTP exchanges with trimmed content for efficiency
    http_exchanges = db.list_job_http_exchanges(job_id, use_trimmed=True)
    metrics = compute_job_metrics(job_dict, http_exchanges)
    job_model_dict = job_model.model_dump()
    job_model_dict.update(metrics)

    # Update the Job model instance with metrics
    job_model_with_metrics = Job(**job_model_dict)

    # Only persist token usage if job is not running
    if job_model_with_metrics.status != JobStatus.RUNNING:
        db.update_job(
            job_id,
            {
                'total_input_tokens': metrics['total_input_tokens'],
                'total_output_tokens': metrics['total_output_tokens'],
            },
        )

    return job_model_with_metrics


@job_router.get('/jobs/queue/status')
async def get_queue_status(_: str = require_api_key):
    """Get the current status of the job queue."""
    async with job_queue_lock:
        queue_size = len(job_queue)
        running_job_dict = None
        if running_job_tasks:
            running_job_id_str = next(iter(running_job_tasks.keys()), None)
            if running_job_id_str:
                try:
                    running_job_id = UUID(running_job_id_str)
                    running_job_dict = db.get_job(running_job_id)
                except ValueError:
                    logger.error(
                        f'Invalid UUID format for running job ID: {running_job_id_str}'
                    )
                except Exception as e:
                    logger.error(
                        f'Error fetching running job {running_job_id_str}: {e}'
                    )

    # Check for inconsistencies between database and memory queue
    # Count jobs with QUEUED status in the database
    all_jobs = db.list_jobs(
        limit=1000
    )  # Get a larger number to ensure we get all queued jobs
    db_queued_count = sum(
        1 for job in all_jobs if job.get('status') == JobStatus.QUEUED.value
    )

    # If database shows queued jobs but memory queue is empty or different size, resynchronize
    if db_queued_count != queue_size:
        logger.warning(
            f'Queue inconsistency detected: {queue_size} jobs in memory vs {db_queued_count} in database'
        )
        # Schedule the queue reinitialization task without awaiting it
        asyncio.create_task(job_queue_initializer())

    return {
        'queue_size': queue_size,
        'queued_in_db': db_queued_count,
        'running_job': running_job_dict,  # Return the dict
        'is_processor_running': job_processor_task is not None
        and not job_processor_task.done(),
    }


@job_router.post(
    '/targets/{target_id}/jobs/{job_id}/interrupt/',
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
async def interrupt_job(target_id: UUID, job_id: UUID, request: Request, _: str = require_api_key):
    """Interrupt a running, queued, or pending job."""
    job_id_str = str(job_id)

    # Check if target exists
    if not db.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')

    # Get job data (dictionary)
    job_dict = db.get_job(job_id)
    if not job_dict:
        raise HTTPException(status_code=404, detail='Job not found')

    # Check if job belongs to target
    if job_dict['target_id'] != target_id:
        raise HTTPException(status_code=404, detail='Job not found for this target')

    # Create Job model instance to access status easily
    job_model = Job(**job_dict)

    # Check job status
    current_status = job_model.status

    interrupted = False

    # Interrupt running job
    if current_status == JobStatus.RUNNING:
        async with job_queue_lock:
            if job_id_str in running_job_tasks:
                task = running_job_tasks[job_id_str]
                if not task.done():
                    task.cancel()
                    interrupted = True
                    logger.info(f'Attempting to interrupt running job {job_id_str}')
                    # The task cancellation will handle status update to ERROR
                else:
                    logger.warning(
                        f'Tried to interrupt job {job_id_str}, but task was already done.'
                    )
            else:
                logger.warning(
                    f'Tried to interrupt job {job_id_str}, but it was not found in running tasks.'
                )
                # Consider updating status to ERROR here if it should be considered an error state
                db.update_job_status(job_id, JobStatus.ERROR)
                add_job_log(
                    job_id_str,
                    'system',
                    'Job interrupt requested, but job was not actively running.',
                )

    # Remove from queue if queued
    elif current_status == JobStatus.QUEUED:
        async with job_queue_lock:
            global job_queue
            initial_queue_size = len(job_queue)
            job_queue = [j for j in job_queue if j.id != job_id]
            if len(job_queue) < initial_queue_size:
                interrupted = True
                db.update_job_status(job_id, JobStatus.ERROR)
                add_job_log(
                    job_id_str,
                    'system',
                    'Job removed from queue due to interrupt request.',
                )
                logger.info(f'Removed queued job {job_id_str} from queue.')
            else:
                logger.warning(
                    f'Tried to interrupt queued job {job_id_str}, but it was not found in the queue.'
                )
                # If not in queue, it might have finished or errored already. Ensure status reflects this.
                # Optionally check current DB status and update if needed
                if db.get_job(job_id)['status'] == JobStatus.QUEUED:
                    db.update_job_status(job_id, JobStatus.ERROR)
                    add_job_log(
                        job_id_str,
                        'system',
                        'Job interrupt requested, but job was not found in queue (updated status to error).',
                    )

    # If pending or any other interruptible state, just mark as error
    elif current_status not in [JobStatus.SUCCESS, JobStatus.ERROR]:
        interrupted = True
        db.update_job_status(job_id, JobStatus.ERROR)
        add_job_log(
            job_id_str,
            'system',
            f"Job interrupted in state '{current_status}'. Status set to ERROR.",
        )
        logger.info(f"Interrupted job {job_id_str} in state '{current_status}'.")

    if interrupted:
        capture_job_interrupted(request, job_model, current_status)
        return {'message': f'Job {job_id} interrupt requested.'}
    else:
        # Check if the job is in a terminal state that cannot be interrupted
        terminal_states = [JobStatus.SUCCESS, JobStatus.ERROR, JobStatus.CANCELED]
        if current_status in terminal_states:
            raise HTTPException(
                status_code=400,
                detail=f"Job {job_id} is already in a terminal state ('{current_status}') and cannot be interrupted.",
            )
        else:
            # This is a fallback - should only happen if there's a logic error
            raise HTTPException(
                status_code=500,
                detail=f"Failed to interrupt job {job_id} in state '{current_status}' for unknown reason.",
            )


@job_router.post('/targets/{target_id}/jobs/{job_id}/cancel/')
async def cancel_job(target_id: UUID, job_id: UUID, request: Request, _: str = require_api_key):
    """Cancel a job and mark its status as 'canceled'."""
    job_id_str = str(job_id)

    # Check if target exists
    if not db.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')

    # Get job data (dictionary)
    job_dict = db.get_job(job_id)
    if not job_dict:
        raise HTTPException(status_code=404, detail='Job not found')

    # Check if job belongs to target
    if job_dict['target_id'] != target_id:
        raise HTTPException(status_code=404, detail='Job not found for this target')

    # Create Job model instance to access status easily
    job_model = Job(**job_dict)

    # Check job status
    current_status = job_model.status

    canceled = False

    # Only allow cancellation on QUEUED and PENDING states
    if current_status == JobStatus.QUEUED:
        async with job_queue_lock:
            global job_queue
            initial_queue_size = len(job_queue)
            job_queue = [j for j in job_queue if j.id != job_id]
            if len(job_queue) < initial_queue_size:
                canceled = True
                db.update_job_status(job_id, JobStatus.CANCELED)
                add_job_log(job_id_str, 'system', 'Job canceled by user request.')
                logger.info(f'Canceled queued job {job_id_str}.')
            else:
                logger.warning(
                    f'Tried to cancel queued job {job_id_str}, but it was not found in the queue.'
                )
                # If not in queue, it might have finished or errored already. Ensure status reflects this.
                if db.get_job(job_id)['status'] == JobStatus.QUEUED:
                    db.update_job_status(job_id, JobStatus.CANCELED)
                    add_job_log(
                        job_id_str,
                        'system',
                        'Job cancel requested, but job was not found in queue (updated status to canceled).',
                    )
                    canceled = True

    # If pending, just mark as canceled
    elif current_status == JobStatus.PENDING:
        canceled = True
        db.update_job_status(job_id, JobStatus.CANCELED)
        add_job_log(job_id_str, 'system', f"Job canceled in state '{current_status}'.")
        logger.info(f"Canceled job {job_id_str} in state '{current_status}'.")

    if canceled:
        capture_job_canceled(request, job_model)
        return {'message': f'Job {job_id} canceled successfully.'}
    else:
        # Check if the job is in a state that cannot be canceled
        non_cancelable_states = [
            JobStatus.RUNNING,
            JobStatus.SUCCESS,
            JobStatus.ERROR,
            JobStatus.CANCELED,
            JobStatus.PAUSED,
        ]
        if current_status in non_cancelable_states:
            raise HTTPException(
                status_code=400,
                detail=f"Job {job_id} is in state '{current_status}' and cannot be canceled. Only pending or queued jobs can be canceled.",
            )
        else:
            # This is a fallback - should only happen if there's a logic error
            raise HTTPException(
                status_code=500,
                detail=f"Failed to cancel job {job_id} in state '{current_status}' for unknown reason.",
            )


@job_router.get(
    '/targets/{target_id}/jobs/{job_id}/logs/',
    response_model=List[JobLogEntry],
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
async def get_job_logs(target_id: UUID, job_id: UUID, request: Request, _: str = require_api_key):
    """Get logs for a specific job."""
    # Check if target exists
    if not db.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')

    # Check if job exists and belongs to target
    job = db.get_target_job(target_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found for this target')

    # Get logs, excluding http_exchange logs as they are accessed via separate endpoint
    logs_data = db.list_job_logs(job_id, exclude_http_exchanges=True)
    # Convert list of dicts to list of JobLogEntry models
    return [JobLogEntry(**log) for log in logs_data]


@job_router.get(
    '/targets/{target_id}/jobs/{job_id}/http_exchanges/',
    response_model=List[HttpExchangeLog],
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
async def get_job_http_exchanges(target_id: UUID, job_id: UUID, _: str = require_api_key):
    """
    Get HTTP exchange logs for a specific job.

    Args:
        target_id: ID of the target
        job_id: ID of the job
    """
    # Check if target exists
    if not db.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')

    # Check if job exists and belongs to target
    job = db.get_target_job(target_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found for this target')

    # Get the exchanges with trimmed content by default for efficiency,
    # or with full content if specifically requested
    exchange_logs_data = db.list_job_http_exchanges(job_id, use_trimmed=True)

    # Convert list of dicts to list of HttpExchangeLog models
    # Ensure the content is parsed correctly if stored as JSON string
    parsed_logs = []
    for log_dict in exchange_logs_data:
        try:
            # If content is a string, try to parse it as JSON
            if isinstance(log_dict.get('content'), str):
                log_dict['content'] = json.loads(log_dict['content'])
            parsed_logs.append(HttpExchangeLog(**log_dict))
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f'Error parsing content for log {log_dict.get("id")}: {e}')
            # Handle error: skip log, use default content, etc.
            # Example: skip this log
            continue

    return parsed_logs


@job_router.post(
    '/targets/{target_id}/jobs/{job_id}/resolve/',
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
async def resolve_job(
    target_id: UUID,
    job_id: UUID,
    result: Annotated[Dict[str, Any], Body(...)],
    request: Request,
):
    """Resolve a job that's in error or paused state.

    This endpoint allows setting a result for a job and marking it as successful.
    If all error/paused jobs for this target are resolved, the queue will automatically resume.
    """
    job_id_str = str(job_id)

    # Check if target exists
    if not db.get_target(target_id):
        raise HTTPException(status_code=404, detail='Target not found')

    # Get job data (dictionary)
    job_dict = db.get_job(job_id)
    if not job_dict:
        raise HTTPException(status_code=404, detail='Job not found')

    # Check if job belongs to target
    if job_dict['target_id'] != target_id:
        raise HTTPException(status_code=404, detail='Job not found for this target')

    # Create Job model instance to access status easily
    job_model = Job(**job_dict)

    # Check if job is in a state that can be resolved (paused or error) # TODO: Can't I just resolve jobs with any status?
    if job_model.status not in [JobStatus.PAUSED, JobStatus.ERROR]:
        raise HTTPException(
            status_code=400,
            detail=f'Cannot resolve job in status {job_model.status.value}',
        )

    # Update the job with success status and the provided result
    updated_job = db.update_job(
        job_id,
        {
            'status': JobStatus.SUCCESS,
            'result': result,
            'completed_at': datetime.now()
            if job_model.completed_at is None
            else job_model.completed_at,
            'updated_at': datetime.now(),
        },
    )

    # Add log for resolving the job
    add_job_log(job_id_str, 'system', 'Job manually resolved')

    # Check if there are any other jobs in error/paused state for this target
    other_paused_jobs = db.list_jobs_by_status_and_target(
        target_id, [JobStatus.PAUSED.value, JobStatus.ERROR.value]
    )

    # If there are no other paused/error jobs, the queue can resume automatically
    if not other_paused_jobs or len(other_paused_jobs) == 0:
        add_job_log(
            job_id_str,
            'system',
            f'No more paused/error jobs for target {target_id}, queue can resume',
        )

        # Process the next job if any
        asyncio.create_task(process_next_job())

    capture_job_resolved(request, updated_job, manual_resolution=True)

    return updated_job


@job_router.post('/jobs/queue/resync', include_in_schema=False)
async def resync_queue(_: str = require_api_key):
    """Manually resynchronize the job queue with the database.

    This is useful for troubleshooting situations where jobs are in the database
    but not being processed by the in-memory queue.
    """
    # Get current queue size before resync
    async with job_queue_lock:
        old_queue_size = len(job_queue)

    # Count jobs with QUEUED status in the database before resync
    all_jobs = db.list_jobs(
        limit=1000
    )  # Get a larger number to ensure we get all queued jobs
    db_queued_count_before = sum(
        1 for job in all_jobs if job.get('status') == JobStatus.QUEUED.value
    )

    # Check if there's an inconsistency
    if old_queue_size != db_queued_count_before:
        logger.warning(
            f'Queue inconsistency detected: {old_queue_size} jobs in memory vs {db_queued_count_before} in database'
        )

    # Reinitialize the queue
    await job_queue_initializer()

    # Get updated queue status after resync
    async with job_queue_lock:
        new_queue_size = len(job_queue)
        is_processor_running = (
            job_processor_task is not None and not job_processor_task.done()
        )

    # Count jobs with QUEUED status in the database after resync
    all_jobs = db.list_jobs(limit=1000)
    db_queued_count_after = sum(
        1 for job in all_jobs if job.get('status') == JobStatus.QUEUED.value
    )

    return {
        'message': 'Queue resynchronized with database',
        'previous_queue_size': old_queue_size,
        'current_queue_size': new_queue_size,
        'queued_in_db_before': db_queued_count_before,
        'queued_in_db_after': db_queued_count_after,
        'is_processor_running': is_processor_running,
    }


@job_router.post(
    '/targets/{target_id}/jobs/{job_id}/resume/',
    response_model=Job,
    tags=['Jobs'],
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
async def resume_job(target_id: UUID, job_id: UUID, request: Request, _: str = require_api_key):
    """Resumes a paused or error job by setting its status to queued."""
    job_id_str = str(job_id)
    logger.info(f'Received request to resume job {job_id_str}')

    # Fetch the job details from DB
    job_data = db.get_job(job_id)
    if not job_data:
        logger.warning(f'Resume failed: Job {job_id_str} not found.')
        raise HTTPException(status_code=404, detail=f'Job {job_id} not found.')

    # Check if the target_id matches
    if str(job_data.get('target_id')) != str(target_id):
        logger.warning(
            f'Resume failed: Job {job_id_str} target mismatch (expected {target_id}, found {job_data.get("target_id")}).'
        )
        raise HTTPException(
            status_code=404, detail=f'Job {job_id} not found for target {target_id}.'
        )

    current_status = job_data.get('status')

    # Allow resuming from PAUSED or ERROR state
    if current_status not in [JobStatus.PAUSED.value, JobStatus.ERROR.value]:
        logger.warning(
            f"Resume failed: Job {job_id_str} is in state '{current_status}', not in ['{JobStatus.PAUSED.value}', '{JobStatus.ERROR.value}']."
        )
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} cannot be resumed from state '{current_status}'. Only paused or error jobs can be resumed.",
        )

    # Create job object and enqueue it
    job_obj = Job(**job_data)
    job_obj.status = JobStatus.QUEUED  # Set status to QUEUED instead of PAUSED
    await enqueue_job(job_obj)

    # Add log entry for the resume action
    add_job_log(job_id_str, 'system', f'Job resumed from {current_status} state')

    capture_job_resumed(request, job_obj)

    return job_obj
