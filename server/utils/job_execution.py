"""
Job execution logic.

This module provides functions for executing jobs in the API Gateway.

Queue Pause Logic:
- A target's job queue is implicitly paused when any job for that target enters
  the ERROR or PAUSED state.
- The queue remains paused until all ERROR/PAUSED jobs are resolved.
- No explicit pause flag is stored in the database; the pause state is inferred
  by checking for jobs in ERROR/PAUSED state.
"""

import asyncio
import logging
import traceback
from datetime import datetime

from server.models.base import Job, JobStatus
from server.utils.db_dependencies import TenantAwareDatabaseService
from server.utils.telemetry import capture_job_resolved
from server.utils.job_logging import add_job_log
from server.utils.job_callbacks import (
    _create_api_response_callback,
    _create_tool_callback,
    _create_output_callback,
)
from server.utils.job_locks import get_target_lock, _check_preconditions_and_set_running

# Set up logging
logger = logging.getLogger(__name__)

# Dictionary to store running job tasks
running_job_tasks = {}

# Track targets that already have sessions being launched
targets_with_pending_sessions = set()
targets_with_pending_sessions_lock = asyncio.Lock()


# Main job execution logic
async def execute_api_in_background_with_tenant(job: Job, tenant_schema: str):
    """Execute a job's API call in the background."""
    # Import core only when needed
    from server.core import APIGatewayCore
    from server.database.multi_tenancy import with_db

    job_id_str = str(job.id)

    # Track token usage for this job - Use a list to allow modification by nonlocal callback
    running_token_total_ref = [0]

    # Add initial job log
    add_job_log(job_id_str, 'system', 'Queue picked up job', tenant_schema)

    # Flag to track if we're requeuing due to a conflict
    requeuing_due_to_conflict = False

    # Acquire lock before precondition check - lock is released by helper if check fails early
    await get_target_lock(job.target_id, tenant_schema)  # Get lock instance

    try:
        # Check preconditions and set status to RUNNING
        (
            can_proceed,
            requeuing_due_to_conflict,
        ) = await _check_preconditions_and_set_running(job, job_id_str, tenant_schema)

        if not can_proceed:
            # Preconditions failed, helper function handled logging/status updates/requeuing
            # The helper function already cleaned up the lock if it failed early.
            # If it's requeuing, the finally block below should skip cleanup.
            return  # Exit the function

        # Create callbacks using helper functions
        api_response_callback = _create_api_response_callback(
            job_id_str, running_token_total_ref, tenant_schema
        )
        tool_callback = _create_tool_callback(job_id_str, tenant_schema)
        output_callback = _create_output_callback(job_id_str, tenant_schema)

        try:
            # Create tenant-aware database service for the core
            with with_db(tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                core = APIGatewayCore(tenant_schema=tenant_schema, db_tenant=db_service)

                # Wrap the execute_api call in its own try-except block to better handle cancellation
                api_response = await core.execute_api(
                    job_id=job_id_str,
                    api_response_callback=api_response_callback,
                    tool_callback=tool_callback,
                    output_callback=output_callback,
                    session_id=str(job.session_id),
                )

            # Update job with result and API exchanges using tenant-aware database service
            with with_db(tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                updated_job = db_service.update_job(
                    job.id,
                    {
                        'status': api_response.status,
                        'result': api_response.extraction,
                        'completed_at': datetime.now(),
                        'updated_at': datetime.now(),
                    },
                )

            # Check if the job status is paused or error, which will implicitly pause the target's queue
            if api_response.status in [JobStatus.PAUSED, JobStatus.ERROR]:
                logger.info(
                    f'Target {job.target_id} queue will be paused due to job {api_response.status.value}'
                )
                # special message for api credits exceeded
                if (
                    api_response.status == JobStatus.PAUSED
                    and 'API Credits Exceeded' in str(api_response.reason)
                ):
                    add_job_log(
                        job_id_str,
                        'error',
                        f'Target {job.target_id} queue will be paused due to insufficient credits',
                        tenant_schema,
                    )
                else:
                    add_job_log(
                        job_id_str,
                        'system',
                        f'Target {job.target_id} queue will be paused due to job {api_response.status.value}',
                        tenant_schema,
                    )

            # Set completion future if it exists
            try:
                from server.routes import jobs

                if (
                    hasattr(jobs, 'completion_futures')
                    and job_id_str in jobs.completion_futures
                ):
                    future = jobs.completion_futures[job_id_str]
                    if not future.done():
                        future.set_result(api_response.status == JobStatus.SUCCESS)
                        logger.info(f'Set completion future for job {job_id_str}')
            except Exception as e:
                logger.error(f'Error setting completion future: {e}')

            msg = f'Job completed with status: {api_response.status}'
            # if status is not success, add the reason
            if api_response.status != JobStatus.SUCCESS:
                msg += f' and reason: {api_response.reason}'
            add_job_log(job_id_str, 'system', msg, tenant_schema)

            # Include token usage in the job data for telemetry
            # TODO: This is a hack to get the token usage into the job data for telemetry,
            # since for some reason that data is returned as None by the DB -> looks like some weird race condition

            from server.utils.job_utils import compute_job_metrics

            # Use tenant-aware database service for getting HTTP exchanges
            with with_db(tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                http_exchanges = db_service.list_job_http_exchanges(
                    job.id, use_trimmed=True
                )
                metrics = compute_job_metrics(updated_job, http_exchanges)
                job_with_tokens = updated_job.copy()
                job_with_tokens['total_input_tokens'] = metrics['total_input_tokens']
                job_with_tokens['total_output_tokens'] = metrics['total_output_tokens']

                capture_job_resolved(None, job_with_tokens, manual_resolution=False)

        except asyncio.CancelledError:
            # Job was cancelled during API execution
            logger.info(f'Job {job_id_str} was cancelled during API execution')

            # Access the token total from the reference list
            running_token_total = running_token_total_ref[0]

            # Check if cancellation was due to token limit
            if (
                running_token_total > 200000
            ):  # TOKEN_LIMIT constant moved to job_callbacks.py
                error_message = f'Job was automatically terminated: exceeded token limit of 200000 tokens (used {running_token_total} tokens)'
                add_job_log(job_id_str, 'system', error_message, tenant_schema)
            else:
                add_job_log(
                    job_id_str, 'system', 'API execution was cancelled', tenant_schema
                )

            # Update job status to ERROR using tenant-aware database service
            with with_db(tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                db_service.update_job(
                    job.id,
                    {
                        'status': JobStatus.ERROR,
                        'error': 'Job was automatically terminated: exceeded token limit'
                        if running_token_total > 200000
                        else 'Job was interrupted by user',
                        'completed_at': datetime.now(),
                        'updated_at': datetime.now(),
                        'total_input_tokens': running_token_total
                        // 2,  # Rough estimate
                        'total_output_tokens': running_token_total
                        // 2,  # Rough estimate
                    },
                )

            # Set completion future with error if it exists
            try:
                from server.routes import jobs

                if (
                    hasattr(jobs, 'completion_futures')
                    and job_id_str in jobs.completion_futures
                ):
                    future = jobs.completion_futures[job_id_str]
                    if not future.done():
                        future.set_exception(asyncio.CancelledError())
                        logger.info(
                            f'Set completion future with error for job {job_id_str}'
                        )
            except Exception as e:
                logger.error(f'Error setting completion future with error: {e}')

            # Re-raise to be caught by the outer try-except
            raise

    except asyncio.CancelledError:
        # Job was cancelled, already handled in interrupt_job or inner try-except
        logger.info(f'Job {job_id_str} was cancelled')

        # Access the token total from the reference list
        running_token_total = running_token_total_ref[0]

        # Check if this was due to token limit
        if (
            running_token_total > 200000
        ):  # TOKEN_LIMIT constant moved to job_callbacks.py
            add_job_log(
                job_id_str,
                'system',
                f'Job execution was cancelled due to token limit ({running_token_total}/200000)',
                tenant_schema,
            )
        else:
            add_job_log(
                job_id_str, 'system', 'Job execution was cancelled', tenant_schema
            )

        # Clean up target lock regardless of errors - Only if not requeuing
        if not requeuing_due_to_conflict:
            try:
                # Acquire target_locks_lock ONCE for the cleanup operations
                from server.utils.job_locks import target_locks, target_locks_lock

                async with target_locks_lock:  # Lock A acquired
                    if job.target_id in target_locks:
                        # Perform the cleanup actions directly here from clean_up_target_lock
                        # to avoid re-acquiring target_locks_lock.
                        del target_locks[job.target_id]
                        logger.info(
                            f'Cleaned up lock for target {job.target_id} (inlined in finally)'
                        )
                    else:
                        # This case means job.target_id was not in target_locks dictionary
                        # when the finally block's lock cleanup section was entered.
                        logger.info(
                            f'Target lock for {job.target_id} not found in target_locks dictionary during finally cleanup.'
                        )
            except Exception as e:
                logger.error(
                    f'Error during inlined target lock cleanup in finally: {str(e)}'
                )

        # Remove the task from running_job_tasks
        if job_id_str in running_job_tasks:
            del running_job_tasks[job_id_str]

        # Ensure completion future is set if it exists and hasn't been set yet
        try:
            from server.routes import jobs

            if (
                hasattr(jobs, 'completion_futures')
                and job_id_str in jobs.completion_futures
            ):
                future = jobs.completion_futures[job_id_str]
                if not future.done():
                    future.set_result(True)
                    logger.info(
                        f'Set completion future in finally block for job {job_id_str}'
                    )
        except Exception as e:
            logger.error(f'Error setting completion future in finally: {e}')

        # Note: process_next_job is deprecated, so we don't call it here

    except Exception as e:
        error_message = str(e)
        error_traceback = ''.join(
            traceback.format_exception(type(e), e, e.__traceback__)
        )

        # Update job with error using tenant-aware database service
        with with_db(tenant_schema) as db_session:
            db_service = TenantAwareDatabaseService(db_session)
            db_service.update_job(
                job.id,
                {
                    'status': JobStatus.ERROR,
                    'error': error_message,
                    'completed_at': datetime.now(),
                    'updated_at': datetime.now(),
                },
            )

        # Log that the target queue will be paused
        logger.info(f'Target {job.target_id} queue will be paused due to job error')
        add_job_log(
            job_id_str,
            'system',
            f'Target {job.target_id} queue will be paused due to job error',
            tenant_schema,
        )

        # Set completion future with error if it exists
        try:
            from server.routes import jobs

            if (
                hasattr(jobs, 'completion_futures')
                and job_id_str in jobs.completion_futures
            ):
                future = jobs.completion_futures[job_id_str]
                if not future.done():
                    future.set_exception(e)
                    logger.info(
                        f'Set completion future with error for job {job_id_str}'
                    )
        except Exception as e:
            logger.error(f'Error setting completion future with error: {e}')

        # Log the error
        add_job_log(
            job_id_str, 'system', f'Error executing job: {error_message}', tenant_schema
        )
        add_job_log(job_id_str, 'error', error_traceback, tenant_schema)
    finally:
        # Only clean up target lock if we're not requeuing due to a conflict
        # This prevents the lock from being released prematurely
        if not requeuing_due_to_conflict:
            try:
                # Acquire target_locks_lock ONCE for the cleanup operations
                from server.utils.job_locks import target_locks, target_locks_lock

                async with target_locks_lock:  # Lock A acquired
                    if job.target_id in target_locks:
                        # Perform the cleanup actions directly here from clean_up_target_lock
                        # to avoid re-acquiring target_locks_lock.
                        del target_locks[job.target_id]
                        logger.info(
                            f'Cleaned up lock for target {job.target_id} (inlined in finally)'
                        )
                    else:
                        # This case means job.target_id was not in target_locks dictionary
                        # when the finally block's lock cleanup section was entered.
                        logger.info(
                            f'Target lock for {job.target_id} not found in target_locks dictionary during finally cleanup.'
                        )
            except Exception as e:
                logger.error(
                    f'Error during inlined target lock cleanup in finally: {str(e)}'
                )

        # Remove the task from running_job_tasks
        if job_id_str in running_job_tasks:
            del running_job_tasks[job_id_str]


async def enqueue_job(job_obj: Job, tenant_schema: str):
    """
    Updates a job's status to QUEUED and enqueues it using Hatchet.

    Args:
        job_obj: The Job Pydantic model instance to enqueue.
        tenant_schema: The tenant schema for this job.
    """
    from server.database.multi_tenancy import with_db
    from server.utils.hatchet_client import enqueue_job_with_hatchet

    # 1. Update status in DB first
    with with_db(tenant_schema) as db_session:
        db_service = TenantAwareDatabaseService(db_session)
        try:
            db_service.update_job_status(job_obj.id, JobStatus.QUEUED)
            logger.info(
                f'Job {job_obj.id} status updated to QUEUED in database for tenant {tenant_schema}.'
            )
            # Update the local object's status as well
            job_obj.status = JobStatus.QUEUED
        except Exception as e:
            logger.error(
                f'Failed to update job {job_obj.id} status to QUEUED in DB for tenant {tenant_schema}: {e}',
                exc_info=True,
            )
            # Raise an exception to prevent potentially queueing a job
            # whose status couldn't be persisted.
            raise RuntimeError(
                f'Failed to update job {job_obj.id} status before queueing for tenant {tenant_schema}'
            ) from e

    # 2. Enqueue job using Hatchet with per-target concurrency
    try:
        hatchet_run_id = enqueue_job_with_hatchet(
            job_id=str(job_obj.id),
            tenant_schema=tenant_schema,
            target_id=str(job_obj.target_id),
        )

        # Add a standard log entry
        log_message = 'Job added to queue'
        add_job_log(str(job_obj.id), 'system', log_message, tenant_schema)
        logger.info(
            f'Job {job_obj.id} enqueued with Hatchet (run ID: {hatchet_run_id}) '
            f'for tenant {tenant_schema} target {job_obj.target_id}'
        )

    except Exception as e:
        logger.error(
            f'Failed to enqueue job {job_obj.id} with Hatchet for tenant {tenant_schema}: {e}',
            exc_info=True,
        )
        # Update job status back to ERROR since we couldn't enqueue it
        with with_db(tenant_schema) as db_session:
            db_service = TenantAwareDatabaseService(db_session)
            db_service.update_job_status(job_obj.id, JobStatus.ERROR)

        raise RuntimeError(
            f'Failed to enqueue job {job_obj.id} with Hatchet for tenant {tenant_schema}'
        ) from e
