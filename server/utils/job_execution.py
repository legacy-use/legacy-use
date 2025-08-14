"""
Job execution logic backed by Postgres leases.

Queue Pause Logic:
- A target's job queue is implicitly paused when any job for that target enters
  the ERROR or PAUSED state (checked in claim query).
"""

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Dict, List
from uuid import UUID
import os
import socket
import time


# Remove direct import of APIGatewayCore
from server.models.base import Job, JobStatus, JobCreate
from server.settings import settings
from server.utils.db_dependencies import TenantAwareDatabaseService
from server.utils.telemetry import capture_job_resolved
from server.utils.job_logging import (
    add_job_log,
    _create_api_response_callback,
    _create_tool_callback,
    _create_output_callback,
)

# Add import for session management functions

# Set up logging
logger = logging.getLogger(__name__)


running_job_tasks: Dict[str, asyncio.Task] = {}
tenant_worker_tasks: Dict[str, List[asyncio.Task]] = {}
tenant_worker_lock = asyncio.Lock()
WORKER_ID = f'{socket.gethostname()}:{os.getpid()}'

# When set, workers will not claim new jobs and will exit their loops after
# finishing any in-flight job. Used to support graceful shutdown.
_drain_mode_event: asyncio.Event | None = None


def _get_drain_event() -> asyncio.Event:
    global _drain_mode_event
    if _drain_mode_event is None:
        _drain_mode_event = asyncio.Event()
    return _drain_mode_event


def is_draining() -> bool:
    return _get_drain_event().is_set()


async def start_workers_for_all_tenants():
    """Start a worker loop per active tenant."""
    logger.info('Starting worker loops for all active tenants...')
    from server.utils.tenant_utils import get_active_tenants

    tenants = get_active_tenants()
    for tenant in tenants:
        await start_worker_for_tenant(tenant['schema'])


async def start_worker_for_tenant(tenant_schema: str):
    async with tenant_worker_lock:
        existing_tasks = tenant_worker_tasks.get(tenant_schema, [])
        # Prune finished tasks
        existing_tasks = [t for t in existing_tasks if not t.done()]

        desired_concurrency = max(1, getattr(settings, 'JOB_WORKERS_PER_TENANT', 1))
        missing = desired_concurrency - len(existing_tasks)
        if missing > 0:
            logger.info(
                f'Starting {missing} worker loop(s) for tenant {tenant_schema} (target={desired_concurrency})'
            )
            new_tasks = [
                asyncio.create_task(worker_loop_for_tenant(tenant_schema))
                for _ in range(missing)
            ]
            existing_tasks.extend(new_tasks)

        tenant_worker_tasks[tenant_schema] = existing_tasks


async def worker_loop_for_tenant(tenant_schema: str):
    from server.database.multi_tenancy import with_db

    while True:
        try:
            # If draining is active, do not claim new work. Exit the loop so the
            # task can finish once any in-flight job has completed.
            if is_draining():
                logger.info(
                    f'Worker loop for tenant {tenant_schema} exiting due to drain mode'
                )
                return
            # Expire stale RUNNING jobs for this tenant, then claim next in one session
            with with_db(tenant_schema) as db_session:
                db = TenantAwareDatabaseService(db_session)
                db.expire_stale_running_jobs()
                claimed = db.claim_next_job(WORKER_ID, tenant_schema=tenant_schema)
            if not claimed:
                await asyncio.sleep(0.5)
                continue
            job = Job(**claimed)
            try:
                exec_task = asyncio.create_task(
                    execute_api_in_background_with_tenant(job, tenant_schema)
                )
                lease_task = asyncio.create_task(
                    _lease_heartbeat(job, tenant_schema, exec_task)
                )
                running_job_tasks[str(job.id)] = exec_task
                try:
                    await exec_task
                finally:
                    running_job_tasks.pop(str(job.id), None)
            finally:
                lease_task.cancel()
        except Exception as e:
            logger.error(f'Worker loop error (tenant={tenant_schema}): {e}')
            await asyncio.sleep(1.0)


async def initiate_graceful_shutdown(timeout_seconds: int = 300) -> None:
    """Enter drain mode and wait for workers to finish in-flight jobs.

    - Signals worker loops to stop claiming new jobs
    - Waits for tenant worker tasks to complete (each at most one in-flight job)
    - If timeout elapses, cancels remaining job tasks
    """
    drain_event = _get_drain_event()
    if not drain_event.is_set():
        logger.info('Entering drain mode: stopping new job claims')
        drain_event.set()
    else:
        logger.info('Drain mode already active')

    # Snapshot tasks to await
    all_tasks: List[asyncio.Task] = []
    for task_list in tenant_worker_tasks.values():
        if task_list:
            all_tasks.extend(task_list)
    tasks_to_await = [t for t in all_tasks if t is not None]
    if not tasks_to_await:
        logger.info('No tenant worker tasks running; shutdown can proceed immediately')
        return

    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks_to_await, return_exceptions=True),
            timeout=timeout_seconds,
        )
        logger.info('All tenant worker tasks completed during drain window')
    except asyncio.TimeoutError:
        logger.warning(
            f'Graceful shutdown timeout ({timeout_seconds}s) reached; cancelling in-flight jobs'
        )
        # Best-effort cancel any remaining running job tasks
        for job_id, task in list(running_job_tasks.items()):
            if not task.done():
                logger.info(f'Cancelling in-flight job task {job_id}')
                task.cancel()
        # Await cancellation completion (best-effort, short timeout)
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *[t for t in running_job_tasks.values()], return_exceptions=True
                ),
                timeout=10,
            )
        except asyncio.TimeoutError:
            logger.warning('Timed out waiting for in-flight job tasks to cancel')


async def _lease_heartbeat(job: Job, tenant_schema: str, exec_task: asyncio.Task):
    from server.database.multi_tenancy import with_db

    try:
        while True:
            await asyncio.sleep(2)
            with with_db(tenant_schema) as db_session:
                db = TenantAwareDatabaseService(db_session)
                # Renew lease and check for cancel signal
                db.renew_job_lease(job.id, WORKER_ID)
                if db.is_job_cancel_requested(job.id):
                    try:
                        exec_task.cancel()
                    finally:
                        return
    except asyncio.CancelledError:
        return


#


# Wait for session readiness before execution
async def _wait_for_session_ready(
    *, session_id: UUID, tenant_schema: str, max_wait_seconds: int = 90
) -> tuple[bool, str]:
    """Poll session until its container is healthy or timeout.

    Returns (is_ready, reason_if_not_ready).
    """
    from server.database.multi_tenancy import with_db
    from server.utils.db_dependencies import TenantAwareDatabaseService
    from server.utils.docker_manager import check_target_container_health

    start_ts = time.monotonic()
    last_reason = 'Waiting for session container to become healthy'

    while time.monotonic() - start_ts < max_wait_seconds:
        try:
            with with_db(tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                sess = db_service.get_session(session_id)
            if not sess:
                return False, 'Session not found'

            state = sess.get('state')
            container_ip = sess.get('container_ip')
            if state in ['destroying', 'destroyed']:
                return False, f'Session is {state}'
            if state == 'error':
                return False, 'Session is in error state'

            if container_ip:
                try:
                    health = await check_target_container_health(container_ip)
                    if health.get('healthy'):
                        return True, 'Health check successful'
                    last_reason = health.get('reason', 'Container not healthy yet')
                except Exception as e:
                    last_reason = f'Health check error: {str(e)}'
            else:
                last_reason = 'Container IP not yet available'
        except Exception as e:
            last_reason = f'Error while checking session readiness: {str(e)}'

        await asyncio.sleep(2)

    return False, f'Timeout waiting for session to become ready: {last_reason}'


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

    try:
        # Already RUNNING due to DB claim

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

                # If a session is attached to this job, wait for it to be ready before executing
                if job.session_id:
                    add_job_log(
                        job_id_str,
                        'system',
                        'Waiting for session to become ready before execution',
                        tenant_schema,
                    )
                    is_ready, not_ready_reason = await _wait_for_session_ready(
                        session_id=job.session_id, tenant_schema=tenant_schema
                    )
                    if not is_ready:
                        updated_job = db_service.update_job(
                            job.id,
                            {
                                'status': JobStatus.PAUSED,
                                'error': not_ready_reason,
                                'completed_at': datetime.now(),
                                'updated_at': datetime.now(),
                            },
                        )
                        logger.info(
                            f'Target {job.target_id} queue will be paused due to job paused'
                        )
                        add_job_log(
                            job_id_str,
                            'system',
                            f'Target {job.target_id} queue will be paused due to job paused',
                            tenant_schema,
                        )

                        add_job_log(
                            job_id_str,
                            'system',
                            f'Job paused: {not_ready_reason}',
                            tenant_schema,
                        )
                        return

                core = APIGatewayCore(tenant_schema=tenant_schema, db_tenant=db_service)

                # Wrap the execute_api call in its own try-except block to better handle cancellation
                api_response = await core.execute_api(
                    job_id=job.id,
                    api_response_callback=api_response_callback,
                    tool_callback=tool_callback,
                    output_callback=output_callback,
                    session_id=(str(job.session_id) if job.session_id else None),
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
            if running_token_total > settings.TOKEN_LIMIT:
                error_message = f'Job was automatically terminated: exceeded token limit of {settings.TOKEN_LIMIT} tokens (used {running_token_total} tokens)'
                add_job_log(job_id_str, 'system', error_message, tenant_schema)
            else:
                add_job_log(
                    job_id_str, 'system', 'API execution was cancelled', tenant_schema
                )

            # Update job status: PAUSED if user-interrupted, ERROR if token limit
            with with_db(tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                user_interrupted = running_token_total <= settings.TOKEN_LIMIT
                status_value = JobStatus.PAUSED if user_interrupted else JobStatus.ERROR
                error_value = (
                    'Job was interrupted by user'
                    if user_interrupted
                    else 'Job was automatically terminated: exceeded token limit'
                )
                db_service.update_job(
                    job.id,
                    {
                        'status': status_value,
                        'error': error_value,
                        'completed_at': datetime.now(),
                        'updated_at': datetime.now(),
                        'cancel_requested': False,
                        'total_input_tokens': running_token_total
                        // 2,  # Rough estimate
                        'total_output_tokens': running_token_total
                        // 2,  # Rough estimate
                    },
                )

            # Re-raise to be caught by the outer try-except
            raise

    except asyncio.CancelledError:
        # Job was cancelled, already handled in interrupt_job or inner try-except
        logger.info(f'Job {job_id_str} was cancelled')

        # Access the token total from the reference list
        running_token_total = running_token_total_ref[0]

        # Check if this was due to token limit
        if running_token_total > settings.TOKEN_LIMIT:
            add_job_log(
                job_id_str,
                'system',
                f'Job execution was cancelled due to token limit ({running_token_total}/{settings.TOKEN_LIMIT})',
                tenant_schema,
            )
        else:
            add_job_log(
                job_id_str, 'system', 'Job execution was cancelled', tenant_schema
            )

        # No in-memory locks to clean up

        # Remove the task from running_job_tasks
        if job_id_str in running_job_tasks:
            del running_job_tasks[job_id_str]

        # No chained processing here; worker loop will pick next claim

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

        # Log the error
        add_job_log(
            job_id_str, 'system', f'Error executing job: {error_message}', tenant_schema
        )
        add_job_log(job_id_str, 'error', error_traceback, tenant_schema)
    finally:
        if job_id_str in running_job_tasks:
            del running_job_tasks[job_id_str]


async def enqueue_job(job_obj: Job, tenant_schema: str):
    """
    Updates a job's status to QUEUED, adds it to the tenant-specific queue,
    logs the event, and ensures the job processor task is running.

    Args:
        job_obj: The Job Pydantic model instance to enqueue.
        tenant_schema: The tenant schema for this job.
    """
    from server.database.multi_tenancy import with_db

    with with_db(tenant_schema) as db_session:
        db_service = TenantAwareDatabaseService(db_session)
        db_service.update_job_status(job_obj.id, JobStatus.QUEUED)
    add_job_log(str(job_obj.id), 'system', 'Job added to queue', tenant_schema)
    await start_worker_for_tenant(tenant_schema)


async def create_and_enqueue_job(
    target_id: UUID, job_create: JobCreate, tenant_schema: str
) -> Job:
    """Create a job for target and enqueue it. Handles session and API version."""
    from server.database.multi_tenancy import with_db
    from server.core import APIGatewayCore

    # Build initial job data
    job_data = job_create.model_dump()
    job_data['target_id'] = target_id

    # Ensure session
    if not job_data.get('session_id'):
        try:
            with with_db(tenant_schema) as db_session:
                db = TenantAwareDatabaseService(db_session)
                active = db.has_active_session_for_target(target_id)
                if active['has_active_session']:
                    job_data['session_id'] = active['session']['id']
                else:
                    from server.utils.session_management import (
                        launch_session_for_target,
                    )

                    session_info = await launch_session_for_target(
                        str(target_id), tenant_schema
                    )
                    if session_info:
                        job_data['session_id'] = session_info['id']
        except Exception:
            # If session setup fails, continue without session
            pass

    # Resolve API definition version id
    with with_db(tenant_schema) as db_session:
        db = TenantAwareDatabaseService(db_session)
        core = APIGatewayCore(tenant_schema=tenant_schema, db_tenant=db)
        api_defs = await core.load_api_definitions()
        api_def = api_defs.get(job_create.api_name)
        job_data['api_definition_version_id'] = api_def.version_id

    # Persist job
    with with_db(tenant_schema) as db_session:
        db = TenantAwareDatabaseService(db_session)
        db_job_dict = db.create_job(job_data)

    job_obj = Job(**db_job_dict)
    await enqueue_job(job_obj, tenant_schema)
    return job_obj
