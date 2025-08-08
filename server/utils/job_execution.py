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
import json
import logging
import traceback
from collections import deque
from datetime import datetime
from typing import Any, Dict, List

import httpx

# Remove direct import of APIGatewayCore
from server.models.base import Job, JobStatus
from server.settings import settings
from server.utils.db_dependencies import TenantAwareDatabaseService
from server.utils.telemetry import capture_job_resolved

# Add import for session management functions

# Set up logging
logger = logging.getLogger(__name__)

# Remove global database service - will use TenantAwareDatabaseService per tenant
# db = DatabaseService()


# Dictionary to store running job tasks
running_job_tasks = {}

# Tenant-specific job queues and locks
tenant_job_queues: Dict[str, deque] = {}
tenant_queue_locks: Dict[str, asyncio.Lock] = {}
tenant_processor_tasks: Dict[str, asyncio.Task] = {}
tenant_resources_lock = asyncio.Lock()

# Track targets that already have sessions being launched
targets_with_pending_sessions = set()
targets_with_pending_sessions_lock = asyncio.Lock()

# Add target-specific locks for job status transitions
target_locks = {}
target_locks_lock = asyncio.Lock()


async def initialize_job_queue():
    """Initialize job queues for all active tenants."""
    logger.info('Initializing job queues for all active tenants...')

    from server.utils.tenant_utils import get_active_tenants

    active_tenants = get_active_tenants()

    if not active_tenants:
        logger.warning('No active tenants found during job queue initialization')
        return

    for tenant in active_tenants:
        tenant_schema = tenant['schema']
        logger.info(
            f'Initializing job queue for tenant: {tenant["name"]} (schema: {tenant_schema})'
        )

        try:
            await initialize_job_queue_for_tenant(tenant_schema)
        except Exception as e:
            logger.error(
                f'Failed to initialize job queue for tenant {tenant["name"]}: {e}'
            )
            continue

    logger.info(f'Completed job queue initialization for {len(active_tenants)} tenants')


async def initialize_job_queue_for_tenant(tenant_schema: str):
    """Initialize job queue for a specific tenant."""
    from server.database.multi_tenancy import with_db

    with with_db(tenant_schema) as db_session:
        db_service = TenantAwareDatabaseService(db_session)

        # Get all jobs for this tenant and filter for QUEUED status
        all_jobs = db_service.list_jobs(limit=1000, offset=0)
        queued_jobs = [
            job for job in all_jobs if job.get('status') == JobStatus.QUEUED.value
        ]

        if not queued_jobs:
            logger.info(f'No queued jobs found for tenant schema: {tenant_schema}')
            return

        # Initialize tenant-specific queue
        async with tenant_resources_lock:
            tenant_job_queues[tenant_schema] = deque()
            tenant_queue_locks[tenant_schema] = asyncio.Lock()

        # Load queued jobs into tenant-specific queue
        async with tenant_queue_locks[tenant_schema]:
            for job_dict in queued_jobs:
                # Double-check job status
                latest_job = db_service.get_job(job_dict['id'])
                if latest_job and latest_job.get('status') == JobStatus.QUEUED.value:
                    job_obj = Job(**job_dict)
                    logger.info(
                        f'Loading queued job {job_obj.id} for tenant {tenant_schema}'
                    )
                    tenant_job_queues[tenant_schema].append(job_obj)

            logger.info(
                f'Loaded {len(tenant_job_queues[tenant_schema])} jobs for tenant {tenant_schema}'
            )

            # Start processor for this tenant if we have jobs
            if tenant_job_queues[tenant_schema]:
                await start_job_processor_for_tenant(tenant_schema)


async def start_job_processor_for_tenant(tenant_schema: str):
    """Start job processor for a specific tenant."""
    async with tenant_resources_lock:
        if (
            tenant_schema not in tenant_processor_tasks
            or tenant_processor_tasks[tenant_schema] is None
            or tenant_processor_tasks[tenant_schema].done()
        ):
            logger.info(f'Starting job processor for tenant: {tenant_schema}')
            tenant_processor_tasks[tenant_schema] = asyncio.create_task(
                process_job_queue_for_tenant(tenant_schema)
            )


async def process_job_queue_for_tenant(tenant_schema: str):
    """Process jobs for a specific tenant."""
    logger.info(f'Starting job queue processor for tenant: {tenant_schema}')

    while True:
        try:
            async with tenant_queue_locks[tenant_schema]:
                if not tenant_job_queues[tenant_schema]:
                    break

                # Ensure the queue is a deque before calling popleft
                queue = tenant_job_queues[tenant_schema]
                if not isinstance(queue, deque):
                    logger.warning(
                        f'Queue for tenant {tenant_schema} is not a deque, converting...'
                    )
                    tenant_job_queues[tenant_schema] = deque(queue)
                    queue = tenant_job_queues[tenant_schema]

                job = queue.popleft()

            # Process the job using tenant-aware database service
            await process_job_with_tenant(job, tenant_schema)

        except Exception as e:
            logger.error(f'Error processing job for tenant {tenant_schema}: {e}')
            await asyncio.sleep(1)

    logger.info(f'Job queue processor finished for tenant: {tenant_schema}')


async def process_job_with_tenant(job: Job, tenant_schema: str):
    """Process a job using tenant-aware database service."""

    # Execute the job using the existing execute_api_in_background function
    # but with tenant-aware database service
    task = asyncio.create_task(
        execute_api_in_background_with_tenant(job, tenant_schema)
    )
    running_job_tasks[str(job.id)] = task

    # Wait for the job to complete
    try:
        await task
    except Exception as e:
        logger.error(
            f'Error executing job {job.id} for tenant {tenant_schema}: {str(e)}'
        )

    # Remove the job from running_job_tasks
    if str(job.id) in running_job_tasks:
        del running_job_tasks[str(job.id)]


# Export the function to be used in the main FastAPI app startup
job_queue_initializer = initialize_job_queue


def trim_base64_images(data):
    """
    Recursively search and trim base64 image data in content structure.

    This function traverses a nested dictionary/list structure and replaces
    base64 image data with "..." to reduce log size.
    """
    if isinstance(data, dict):
        # Check if this is an image content entry with base64 data
        if (
            data.get('type') == 'image'
            and isinstance(data.get('source'), dict)
            and data['source'].get('type') == 'base64'
            and 'data' in data['source']
        ):
            # Replace the base64 data with "..."
            data['source']['data'] = '...'
        else:
            # Recursively process all dictionary values
            for key, value in data.items():
                data[key] = trim_base64_images(value)
    elif isinstance(data, list):
        # Recursively process all list items
        for i, item in enumerate(data):
            data[i] = trim_base64_images(item)

    return data


def trim_http_body(body):
    """
    Process an HTTP body (request or response) to trim base64 image data.

    Handles both string (JSON) and dictionary body formats.
    Returns the trimmed body.
    """
    try:
        # If body is a string that might be JSON, parse it
        if isinstance(body, str):
            try:
                body_json = json.loads(body)
                return json.dumps(trim_base64_images(body_json))
            except json.JSONDecodeError:
                # Not valid JSON, keep as is or set to empty if too large
                if len(body) > 1000:
                    return '<trimmed>'
                return body
        elif isinstance(body, dict):
            return trim_base64_images(body)
        else:
            return body
    except Exception as e:
        logger.error(f'Error trimming HTTP body: {str(e)}')
        return '<trim error>'


# Function to add logs to the database
def add_job_log(job_id: str, log_type: str, content: Any, tenant_schema: str):
    """Add a log entry for a job with tenant context."""
    from server.database.multi_tenancy import with_db

    with with_db(tenant_schema) as db_session:
        db_service = TenantAwareDatabaseService(db_session)

        # Trim base64 images from content for storage
        trimmed_content = trim_base64_images(content)

        log_data = {
            'job_id': job_id,
            'log_type': log_type,
            'content': content,
            'content_trimmed': trimmed_content,
        }

        db_service.create_job_log(log_data)
        logger.info(f'Added {log_type} log for job {job_id} in tenant {tenant_schema}')


async def get_target_lock(target_id, tenant_schema: str):
    """Get target lock for specific tenant."""
    async with target_locks_lock:
        if target_id not in target_locks:
            target_locks[target_id] = asyncio.Lock()
        return target_locks[target_id]


async def clean_up_target_lock(target_id, tenant_schema: str):
    """Clean up target lock for specific tenant."""
    async with target_locks_lock:
        if target_id in target_locks:
            del target_locks[target_id]


# Helper function for precondition checks
async def _check_preconditions_and_set_running(
    job: Job, job_id_str: str, tenant_schema: str
) -> tuple[bool, bool]:
    """Check preconditions with tenant context."""
    from server.database.multi_tenancy import with_db

    with with_db(tenant_schema) as db_session:
        db_service = TenantAwareDatabaseService(db_session)

        # Get the latest job status from database
        latest_job = db_service.get_job(job_id_str)
        if not latest_job:
            logger.error(
                f'Job {job_id_str} not found in database for tenant {tenant_schema}'
            )
            return False, False

        if latest_job.get('status') != JobStatus.QUEUED.value:
            logger.info(
                f'Job {job_id_str} status is {latest_job.get("status")}, not QUEUED for tenant {tenant_schema}'
            )
            return False, False

        # Check if target is available
        target_id = job.target_id
        target_lock = await get_target_lock(target_id, tenant_schema)

        if target_lock.locked():
            logger.info(
                f'Target {target_id} is locked, skipping job {job_id_str} for tenant {tenant_schema}'
            )
            return False, False

        # Try to acquire target lock non-blocking
        if target_lock.locked():
            logger.info(
                f'Could not acquire target lock for {target_id}, skipping job {job_id_str} for tenant {tenant_schema}'
            )
            return False, False

        await target_lock.acquire()

        try:
            # Update job status to RUNNING
            db_service.update_job_status(job_id_str, JobStatus.RUNNING.value)
            logger.info(
                f'Set job {job_id_str} to RUNNING status for tenant {tenant_schema}'
            )
            return True, True
        except Exception as e:
            logger.error(
                f'Failed to update job {job_id_str} status: {e} for tenant {tenant_schema}'
            )
            target_lock.release()
            return False, False


# Helper function to create the API response callback
def _create_api_response_callback(
    job_id_str: str, running_token_total_ref: List[int], tenant_schema: str
):
    """Creates the callback function for handling API responses."""

    def api_response_callback(request, response, error):
        nonlocal running_token_total_ref  # Allow modification of the outer scope variable
        # Create exchange object with full request and response details
        exchange = {
            'timestamp': datetime.now().isoformat(),
            'request': {
                'method': request.method,
                'url': str(request.url),
                'headers': dict(request.headers),
            },
        }

        # Get request body and size
        try:
            # For httpx.Request objects
            if hasattr(request, 'read'):
                # Read the request body without consuming it
                body_bytes = request.read()
                if body_bytes:
                    exchange['request']['body_size'] = len(body_bytes)
                    try:
                        exchange['request']['body'] = body_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        exchange['request']['body'] = '<binary data>'
                else:
                    exchange['request']['body_size'] = 0
                    exchange['request']['body'] = ''
            # For other request objects with content attribute
            elif hasattr(request, 'content') and request.content:
                exchange['request']['body_size'] = len(request.content)
                try:
                    exchange['request']['body'] = request.content.decode('utf-8')
                except UnicodeDecodeError:
                    exchange['request']['body'] = '<binary data>'
            # For other request objects with _content attribute
            elif hasattr(request, '_content') and request._content:
                exchange['request']['body_size'] = len(request._content)
                try:
                    exchange['request']['body'] = request._content.decode('utf-8')
                except UnicodeDecodeError:
                    exchange['request']['body'] = '<binary data>'
            else:
                exchange['request']['body_size'] = 0
                exchange['request']['body'] = ''
        except Exception as e:
            logger.error(f'Error getting request body: {str(e)}')
            exchange['request']['body_size'] = -1
            exchange['request']['body'] = f'<Error retrieving body: {str(e)}>'

        if isinstance(response, httpx.Response):
            exchange['response'] = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
            }

            # Get response body and size
            try:
                # Try to get the response text directly
                if hasattr(response, 'text'):
                    exchange['response']['body'] = response.text
                    exchange['response']['body_size'] = len(
                        response.text.encode('utf-8')
                    )
                # Otherwise try to get the content and decode it
                elif hasattr(response, 'content') and response.content:
                    exchange['response']['body_size'] = len(response.content)
                    try:
                        exchange['response']['body'] = response.content.decode('utf-8')
                    except UnicodeDecodeError:
                        exchange['response']['body'] = '<binary data>'
                else:
                    exchange['response']['body_size'] = 0
                    exchange['response']['body'] = ''
            except Exception as e:
                logger.error(f'Error getting response body: {str(e)}')
                exchange['response']['body_size'] = -1
                exchange['response']['body'] = f'<Error retrieving body: {str(e)}>'

            try:
                if hasattr(response, 'json'):
                    response_data = response.json()
                    if isinstance(response_data, dict):
                        if 'usage' in response_data:
                            usage = response_data['usage']
                            total_tokens = 0

                            # Handle regular input/output tokens
                            if 'input_tokens' in usage:
                                total_tokens += usage['input_tokens']
                                exchange['input_tokens'] = usage['input_tokens']

                            if 'output_tokens' in usage:
                                total_tokens += usage['output_tokens']
                                exchange['output_tokens'] = usage['output_tokens']

                            # Handle cache creation tokens with 1.25x multiplier
                            if 'cache_creation_input_tokens' in usage:
                                cache_creation_tokens = int(
                                    usage['cache_creation_input_tokens'] * 1.25
                                )
                                total_tokens += cache_creation_tokens
                                exchange['cache_creation_tokens'] = (
                                    cache_creation_tokens
                                )

                            # Handle cache read tokens with 0.1x multiplier
                            if 'cache_read_input_tokens' in usage:
                                cache_read_tokens = int(
                                    usage['cache_read_input_tokens'] / 10
                                )
                                total_tokens += cache_read_tokens
                                exchange['cache_read_tokens'] = cache_read_tokens

                            # Update running token total using the reference
                            current_total = running_token_total_ref[0]
                            current_total += total_tokens
                            running_token_total_ref[0] = (
                                current_total  # Modify the list element
                            )

                            # Check if we've exceeded the token limit
                            if current_total > settings.TOKEN_LIMIT:
                                # Add warning about token limit
                                limit_message = f'Token usage limit of {settings.TOKEN_LIMIT} exceeded. Current usage: {current_total}. Job will be interrupted.'
                                exchange['token_limit_exceeded'] = True
                                logger.warning(f'Job {job_id_str}: {limit_message}')
                                add_job_log(
                                    job_id_str, 'system', limit_message, tenant_schema
                                )

                                # Cancel the job by raising an exception
                                # This will be caught in the outer try/except block
                                task = asyncio.current_task()
                                if task:
                                    task.cancel()
            except Exception as e:
                logger.error(f'Error extracting token usage: {repr(e)}')

        if error:
            exchange['error'] = {
                'type': error.__class__.__name__,
                'message': str(error),
            }

        # Add to job logs
        add_job_log(job_id_str, 'http_exchange', exchange, tenant_schema)

    return api_response_callback


# Helper function to create the tool callback
def _create_tool_callback(job_id_str: str, tenant_schema: str):
    """Creates the callback function for handling tool usage."""

    def tool_callback(tool_result, tool_id):
        tool_log = {
            'tool_id': tool_id,
            'output': tool_result.output if hasattr(tool_result, 'output') else None,
            'error': tool_result.error if hasattr(tool_result, 'error') else None,
            'has_image': hasattr(tool_result, 'base64_image')
            and tool_result.base64_image is not None,
        }

        # Include the base64_image data if it exists
        if (
            hasattr(tool_result, 'base64_image')
            and tool_result.base64_image is not None
        ):
            tool_log['base64_image'] = tool_result.base64_image

        add_job_log(job_id_str, 'tool_use', tool_log, tenant_schema)

    return tool_callback


# Helper function to create the output callback
def _create_output_callback(job_id_str: str, tenant_schema: str):
    """Creates the callback function for handling message output."""

    def output_callback(content_block):
        add_job_log(job_id_str, 'message', content_block, tenant_schema)

    return output_callback


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
            if running_token_total > settings.TOKEN_LIMIT:
                error_message = f'Job was automatically terminated: exceeded token limit of {settings.TOKEN_LIMIT} tokens (used {running_token_total} tokens)'
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
                        if running_token_total > settings.TOKEN_LIMIT
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

        # Clean up target lock regardless of errors - Only if not requeuing
        if not requeuing_due_to_conflict:
            try:
                # Acquire target_locks_lock ONCE for the cleanup operations
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


# This function is deprecated - use tenant-specific processing instead
async def process_job_queue():
    """Deprecated: This function is no longer used. Use tenant-specific job processing."""
    logger.warning('process_job_queue is deprecated - use tenant-specific processing')
    raise NotImplementedError('Use tenant-specific job processing')


# This function is deprecated - use tenant-specific processing instead
async def process_next_job():
    """Deprecated: This function is no longer used. Use tenant-specific job processing."""
    logger.warning('process_next_job is deprecated - use tenant-specific processing')
    raise NotImplementedError('Use tenant-specific job processing')


async def enqueue_job(job_obj: Job, tenant_schema: str):
    """
    Updates a job's status to QUEUED, adds it to the tenant-specific queue,
    logs the event, and ensures the job processor task is running.

    Args:
        job_obj: The Job Pydantic model instance to enqueue.
        tenant_schema: The tenant schema for this job.
    """
    from server.database.multi_tenancy import with_db

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

    # 2. Add to tenant-specific queue and manage processor
    async with tenant_resources_lock:
        if tenant_schema not in tenant_job_queues:
            tenant_job_queues[tenant_schema] = deque()
            tenant_queue_locks[tenant_schema] = asyncio.Lock()

    async with tenant_queue_locks[tenant_schema]:
        # Ensure the queue is a deque before operating on it
        queue = tenant_job_queues[tenant_schema]
        if not isinstance(queue, deque):
            logger.warning(
                f'Queue for tenant {tenant_schema} is not a deque, converting...'
            )
            tenant_job_queues[tenant_schema] = deque(queue)
            queue = tenant_job_queues[tenant_schema]

        # Safety check: Avoid adding the same job twice
        if any(j.id == job_obj.id for j in queue):
            logger.warning(
                f'Job {job_obj.id} is already in the queue for tenant {tenant_schema}. Skipping addition.'
            )
            return  # Job already enqueued, nothing more to do

        # Add job to the tenant-specific queue
        queue.append(job_obj)
        # Add a standard log entry
        log_message = 'Job added to queue'  # Use the consistent message
        add_job_log(str(job_obj.id), 'system', log_message, tenant_schema)
        logger.info(
            f"Job {job_obj.id} added to queue for tenant {tenant_schema}. Log message: '{log_message}'"
        )

        # Start processor if not already running
        await start_job_processor_for_tenant(tenant_schema)
