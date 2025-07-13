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
import copy
import json
import logging
import traceback
from collections import deque
from datetime import datetime
from typing import Any, List
from uuid import UUID

import httpx

# Remove direct import of APIGatewayCore
from server.database.service import DatabaseService
from server.models.base import Job, JobStatus
from server.utils.telemetry import capture_job_log_created, capture_job_resolved

# Add import for session management functions
from .session_management import launch_session_for_target

# Set up logging
logger = logging.getLogger(__name__)

# Initialize database only, defer core initialization
db = DatabaseService()

# Constants
TOKEN_LIMIT = 200000  # Maximum number of tokens (input + output) allowed per job

# Dictionary to store running job tasks
running_job_tasks = {}

# Job queue and lock for ensuring only one job runs at a time
job_queue = deque()
job_queue_lock = asyncio.Lock()
job_processor_task = None

# Track targets that already have sessions being launched
targets_with_pending_sessions = set()
targets_with_pending_sessions_lock = asyncio.Lock()

# Add target-specific locks for job status transitions
target_locks = {}
target_locks_lock = asyncio.Lock()


async def initialize_job_queue():
    """Load queued jobs from the database into the in-memory queue."""
    logger.info('Initializing job queue from database...')

    # Get all jobs and filter for QUEUED status
    all_jobs = db.list_jobs(
        limit=1000, offset=0
    )  # Get a larger number to ensure we get all queued jobs
    queued_jobs = [
        job for job in all_jobs if job.get('status') == JobStatus.QUEUED.value
    ]

    if not queued_jobs:
        logger.info('No queued jobs found in the database.')
        return

    # Before loading jobs, clear the existing queue to prevent duplicates
    async with job_queue_lock:
        # Check if there's a queue size inconsistency
        queue_size = len(job_queue)
        if queue_size > 0 and queue_size != len(queued_jobs):
            logger.warning(
                f'Queue inconsistency detected: {queue_size} jobs in memory vs {len(queued_jobs)} in database'
            )

        # Clear the existing queue
        job_queue.clear()

        # Load only jobs that are in QUEUED state - double check current status
        for job_dict in queued_jobs:
            # Get the latest job status to ensure it's still QUEUED
            latest_job = db.get_job(job_dict['id'])
            if latest_job and latest_job.get('status') == JobStatus.QUEUED.value:
                job_obj = Job(**job_dict)
                logger.info(f'Loading queued job {job_obj.id} into memory queue')
                job_queue.append(job_obj)
            else:
                if latest_job:
                    logger.info(
                        f'Skipping job {job_dict["id"]}: status is {latest_job.get("status")}, not QUEUED'
                    )
                else:
                    logger.warning(f'Job {job_dict["id"]} not found in database')

        logger.info(f'Loaded {len(job_queue)} jobs into the queue')

        # Start the job processor - Only start if we have jobs and no processor is running
        global job_processor_task
        if job_queue and (job_processor_task is None or job_processor_task.done()):
            logger.info('Starting job processor during initialization')
            job_processor_task = asyncio.create_task(process_job_queue())
            logger.info('Started job queue processor after initialization')
        else:
            if not job_queue:
                logger.info(
                    'No jobs to process after filtering - not starting processor'
                )
            else:
                logger.info(
                    'Job processor is already running during initialization - not starting a new one'
                )


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
def add_job_log(job_id: str, log_type: str, content: Any):
    """Helper function to add a log entry for a job."""
    try:
        log_data = {'job_id': UUID(job_id), 'log_type': log_type, 'content': content}

        # Create a deep copy of content for HTTP exchanges to avoid modifying the original
        content_trimmed = (
            copy.deepcopy(content) if isinstance(content, dict) else content
        )
        if log_type == 'http_exchange':
            # Process request and response bodies to trim base64 image data
            if 'request' in content_trimmed and 'body' in content_trimmed['request']:
                content_trimmed['request']['body'] = trim_http_body(
                    content_trimmed['request']['body']
                )

            if 'response' in content_trimmed and 'body' in content_trimmed['response']:
                content_trimmed['response']['body'] = trim_http_body(
                    content_trimmed['response']['body']
                )

        log_data['content_trimmed'] = content_trimmed

        db.create_job_log(log_data)
        capture_job_log_created(job_id, log_data)
    except Exception as e:
        logger.error(f'Failed to add log for job {job_id}: {str(e)}')


async def get_target_lock(target_id):
    """Get or create a lock for a specific target."""
    async with target_locks_lock:
        if target_id not in target_locks:
            target_locks[target_id] = asyncio.Lock()
        return target_locks[target_id]


async def clean_up_target_lock(target_id):
    """Remove a target lock when it's no longer needed."""
    async with target_locks_lock:
        if target_id in target_locks:
            del target_locks[target_id]
            logger.info(f'Cleaned up lock for target {target_id}')


# Helper function for precondition checks
async def _check_preconditions_and_set_running(
    job: Job, job_id_str: str
) -> tuple[bool, bool]:
    """
    Checks preconditions for job execution (session state, existing running jobs)
    and sets the job status to RUNNING if checks pass.

    Returns:
        tuple[bool, bool]: (can_proceed, requeued)
    """
    requeuing_due_to_conflict = False

    # Check session state before executing
    session = db.get_session(job.session_id)
    if session and session.get('state') != 'ready':
        # Session is not ready, update job status to ERROR
        session_state = session.get('state', 'unknown')
        error_message = f"Cannot execute job: session is in state '{session_state}' instead of 'ready'"
        logger.warning(f'Job {job_id_str}: {error_message}')
        add_job_log(job_id_str, 'system', error_message)

        db.update_job(
            job.id,
            {
                'status': JobStatus.ERROR,
                'error': error_message,
                'completed_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
            },
        )

        # Log that the target queue will be paused
        logger.info(f'Target {job.target_id} queue will be paused due to job error')
        add_job_log(
            job_id_str,
            'system',
            f'Target {job.target_id} queue will be paused due to job error',
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
                    future.set_exception(ValueError(error_message))
        except Exception as e:
            logger.error(f'Error setting completion future: {e}')

        return False, False  # Cannot proceed, not requeued

    # Acquire target-specific lock before updating job status to RUNNING
    # This ensures only one job per target can be in RUNNING state at a time
    target_lock = await get_target_lock(job.target_id)
    async with target_lock:
        # Check if there's already a running job for this target
        running_jobs = db.list_jobs_by_status_and_target(
            job.target_id, [JobStatus.RUNNING], limit=1
        )

        if running_jobs and len(running_jobs) > 0:
            # There's already a running job for this target, log warning and skip execution
            existing_job_id = running_jobs[0]['id']
            if str(existing_job_id) != job_id_str:  # Not the same job
                error_message = f'Cannot execute job: another job ({existing_job_id}) is already running for target {job.target_id}'
                logger.warning(f'Job {job_id_str}: {error_message}')

                # Use positive list approach - only requeue if job is in QUEUED or PENDING state
                current_job_status = db.get_job(job.id).get('status')
                if current_job_status in [
                    JobStatus.QUEUED.value,
                    JobStatus.PENDING.value,
                ]:
                    logger.info(
                        f'Requeuing job {job_id_str} as it is in state {current_job_status}'
                    )

                    # Requeue the job
                    async with job_queue_lock:
                        job_queue.append(job)

                    # Set the flag to indicate we're requeuing due to conflict
                    requeuing_due_to_conflict = True
                else:
                    logger.info(
                        f'Not requeuing job {job_id_str} as it is in state {current_job_status}, not QUEUED or PENDING'
                    )

                # We are either requeuing or stopping, so cannot proceed
                # Release the lock here since we acquired it but are returning early
                # Note: This might be slightly inefficient if requeuing, but simpler for now
                await clean_up_target_lock(
                    job.target_id
                )  # Clean up lock as we are not proceeding
                return False, requeuing_due_to_conflict  # Cannot proceed

        # No other running jobs for this target, update status to RUNNING
        db.update_job_status(job.id, JobStatus.RUNNING)
        add_job_log(job_id_str, 'system', 'Target is ready to execute job...')

    # If we reached here, preconditions passed, and status is RUNNING
    return True, False  # Can proceed, not requeued


# Helper function to create the API response callback
def _create_api_response_callback(job_id_str: str, running_token_total_ref: List[int]):
    """Creates the callback function for handling API responses."""

    def api_response_callback(request, response, error):
        nonlocal running_token_total_ref  # Allow modification of the outer scope variable
        # Create exchange object with full request and response details
        exchange = {
            'timestamp': datetime.utcnow().isoformat(),
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
                            if current_total > TOKEN_LIMIT:
                                # Add warning about token limit
                                limit_message = f'Token usage limit of {TOKEN_LIMIT} exceeded. Current usage: {current_total}. Job will be interrupted.'
                                exchange['token_limit_exceeded'] = True
                                logger.warning(f'Job {job_id_str}: {limit_message}')
                                add_job_log(job_id_str, 'system', limit_message)

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
        add_job_log(job_id_str, 'http_exchange', exchange)

    return api_response_callback


# Helper function to create the tool callback
def _create_tool_callback(job_id_str: str):
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

        add_job_log(job_id_str, 'tool_use', tool_log)

    return tool_callback


# Helper function to create the output callback
def _create_output_callback(job_id_str: str):
    """Creates the callback function for handling message output."""

    def output_callback(content_block):
        add_job_log(job_id_str, 'message', content_block)

    return output_callback


# Main job execution logic
async def execute_api_in_background(job: Job):
    """Execute a job's API call in the background."""
    # Import core only when needed
    from server.core import APIGatewayCore

    core = APIGatewayCore()

    job_id_str = str(job.id)

    # Track token usage for this job - Use a list to allow modification by nonlocal callback
    running_token_total_ref = [0]

    # Add initial job log
    add_job_log(job_id_str, 'system', 'Queue picked up job')

    # Flag to track if we're requeuing due to a conflict
    requeuing_due_to_conflict = False

    # Acquire lock before precondition check - lock is released by helper if check fails early
    await get_target_lock(job.target_id)  # Get lock instance

    try:
        # Check preconditions and set status to RUNNING
        (
            can_proceed,
            requeuing_due_to_conflict,
        ) = await _check_preconditions_and_set_running(job, job_id_str)

        if not can_proceed:
            # Preconditions failed, helper function handled logging/status updates/requeuing
            # The helper function already cleaned up the lock if it failed early.
            # If it's requeuing, the finally block below should skip cleanup.
            return  # Exit the function

        # Create callbacks using helper functions
        api_response_callback = _create_api_response_callback(
            job_id_str, running_token_total_ref
        )
        tool_callback = _create_tool_callback(job_id_str)
        output_callback = _create_output_callback(job_id_str)

        try:
            # Wrap the execute_api call in its own try-except block to better handle cancellation
            api_response = await core.execute_api(
                job_id=job_id_str,
                api_response_callback=api_response_callback,
                tool_callback=tool_callback,
                output_callback=output_callback,
                session_id=str(job.session_id),
            )

            # Update job with result and API exchanges
            updated_job = db.update_job(
                job.id,
                {
                    'status': api_response.status,
                    'result': api_response.extraction,
                    'completed_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow(),
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
                    )
                else:
                    add_job_log(
                        job_id_str,
                        'system',
                        f'Target {job.target_id} queue will be paused due to job {api_response.status.value}',
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

            add_job_log(
                job_id_str,
                'system',
                f'Job completed with status: {api_response.status} and reason: {api_response.reason}',
            )

            # Include token usage in the job data for telemetry
            # TODO: This is a hack to get the token usage into the job data for telemetry,
            # since for some reason that data is returned as None by the DB -> looks like some weird race condition

            from server.utils.job_utils import compute_job_metrics

            http_exchanges = db.list_job_http_exchanges(job.id, use_trimmed=True)
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
            if running_token_total > TOKEN_LIMIT:
                error_message = f'Job was automatically terminated: exceeded token limit of {TOKEN_LIMIT} tokens (used {running_token_total} tokens)'
                add_job_log(job_id_str, 'system', error_message)
            else:
                add_job_log(job_id_str, 'system', 'API execution was cancelled')

            # Update job status to ERROR
            db.update_job(
                job.id,
                {
                    'status': JobStatus.ERROR,
                    'error': 'Job was automatically terminated: exceeded token limit'
                    if running_token_total > TOKEN_LIMIT
                    else 'Job was interrupted by user',
                    'completed_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow(),
                    'total_input_tokens': running_token_total // 2,  # Rough estimate
                    'total_output_tokens': running_token_total // 2,  # Rough estimate
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
        if running_token_total > TOKEN_LIMIT:
            add_job_log(
                job_id_str,
                'system',
                f'Job execution was cancelled due to token limit ({running_token_total}/{TOKEN_LIMIT})',
            )
        else:
            add_job_log(job_id_str, 'system', 'Job execution was cancelled')

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

        # Process the next job in the queue
        asyncio.create_task(process_next_job())

    except Exception as e:
        error_message = str(e)
        error_traceback = ''.join(
            traceback.format_exception(type(e), e, e.__traceback__)
        )

        # Update job with error
        db.update_job(
            job.id,
            {
                'status': JobStatus.ERROR,
                'error': error_message,
                'completed_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
            },
        )

        # Log that the target queue will be paused
        logger.info(f'Target {job.target_id} queue will be paused due to job error')
        add_job_log(
            job_id_str,
            'system',
            f'Target {job.target_id} queue will be paused due to job error',
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
        add_job_log(job_id_str, 'system', f'Error executing job: {error_message}')
        add_job_log(job_id_str, 'error', error_traceback)
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


async def process_job_queue():
    """Process jobs in the queue one at a time."""
    logger.info('Job queue processor started')

    while True:
        # Get the next job from the queue
        current_job = None
        async with job_queue_lock:
            if not job_queue:
                logger.info('Job queue is empty, stopping processor')
                break

            # Find a job from a target that's not paused
            for _i, job in enumerate(job_queue):
                # Check if target's queue is paused (by looking for ERROR or PAUSED jobs)
                blocking_info = db.is_target_queue_paused(job.target_id)
                if not blocking_info['is_paused']:
                    logger.info(
                        f'Target {job.target_id} queue is not paused: {blocking_info} - processing job {job.id}'
                    )
                    current_job = job
                    job_queue.remove(job)
                    break

            # If all targets' queues with jobs are paused, wait and retry
            if not current_job and job_queue:
                logger.info(
                    'All targets with jobs have paused queues due to ERROR or PAUSED jobs'
                )

        # If no job could be processed because all queues are paused, wait and retry
        if not current_job and job_queue:
            await asyncio.sleep(5)
            continue

        if current_job:
            logger.info(f'Processing job {current_job.id} from queue')

            # Check if job has a session assigned
            if current_job.session_id:
                # Check session state before executing the job
                session = db.get_session(current_job.session_id)
                if session and session.get('state') != 'ready':
                    session_state = session.get('state', 'unknown')

                    # Check if session is in a terminal state (destroying or destroyed)
                    if session_state in ['destroying', 'destroyed']:
                        # Session is in a terminal state
                        error_message = f"Cannot execute job: session is in terminal state '{session_state}'"
                        logger.warning(f'Job {current_job.id}: {error_message}')
                        add_job_log(str(current_job.id), 'system', error_message)

                        # Instead of failing the job, create a new session and reassign it
                        logger.info(
                            f'Creating new session for job {current_job.id} since previous session is in terminal state'
                        )
                        add_job_log(
                            str(current_job.id),
                            'system',
                            'Creating new session since previous session is in terminal state',
                        )

                        # Reset the session_id on the job
                        current_job.session_id = None
                        db.update_job(current_job.id, {'session_id': None})

                        # Requeue the job so it can go through the session assignment process
                        async with job_queue_lock:
                            job_queue.append(current_job)

                        await asyncio.sleep(1)
                        continue
                    else:
                        # Session is not ready but in a non-terminal state, requeue the job
                        logger.info(
                            f'Session {current_job.session_id} not ready (state: {session_state}), requeuing job {current_job.id}'
                        )
                        add_job_log(
                            str(current_job.id),
                            'system',
                            f'Job waiting for session to be ready (current state: {session_state})',
                        )

                        async with job_queue_lock:
                            job_queue.append(current_job)

                    # Wait a short time before processing the next job
                    await asyncio.sleep(1)
                    continue
            else:
                # Job has no session assigned - check if we need to assign one
                # Get an available session for the target
                target_id_str = str(
                    current_job.target_id
                )  # Ensure target_id is a string for UUID conversion and logging
                target_uuid = UUID(target_id_str)
                available_session = db.find_ready_session_for_target(
                    target_id=target_uuid
                )

                if available_session:
                    # Assign the job to this session
                    current_job.session_id = available_session['id']
                    db.update_job(
                        current_job.id, {'session_id': available_session['id']}
                    )
                    add_job_log(
                        str(current_job.id),
                        'system',
                        f'Job assigned to session {available_session["id"]}',
                    )
                else:
                    # No session available, check if we should launch a new one
                    launch_new_session = False

                    # First check if any session is already initializing in the database                       # target_uuid is already defined above when calling db.find_ready_session_for_target
                    db_initializing = db.has_initializing_session_for_target(
                        target_id=target_uuid
                    )
                    if not db_initializing:
                        # No session is initializing in the database, check our in-memory tracking
                        async with targets_with_pending_sessions_lock:
                            if target_id_str not in targets_with_pending_sessions:
                                # No session is being launched for this target yet
                                targets_with_pending_sessions.add(target_id_str)
                                launch_new_session = True
                                logger.info(
                                    f'Added target {target_id_str} to pending sessions set.'
                                )  # Added log
                            else:
                                logger.info(
                                    f'Target {target_id_str} already in pending sessions set.'
                                )  # Added log

                    if launch_new_session:
                        # Launch a new session in the background
                        logger.info(
                            f'No available sessions for target {target_id_str}, launching a new one'
                        )
                        add_job_log(
                            str(current_job.id),
                            'system',
                            f'No available sessions for target {target_id_str}, launching a new one',
                        )
                        # Use the imported function
                        asyncio.create_task(launch_session_for_target(target_id_str))
                    else:
                        # A session is already being launched for this target
                        if db_initializing:
                            reason = 'a session is initializing in the database'
                        else:
                            reason = 'a session is being launched'

                        logger.info(
                            f'No available sessions for target {target_id_str}, but {reason}. Requeuing job {current_job.id}'
                        )
                        add_job_log(
                            str(current_job.id),
                            'system',
                            f'No available sessions for target {target_id_str}, waiting for session launch to complete',
                        )

                    # Requeue the job
                    async with job_queue_lock:
                        job_queue.append(current_job)
                    await asyncio.sleep(5)  # Wait a bit longer before retrying
                    continue

            # Execute the job
            task = asyncio.create_task(execute_api_in_background(current_job))
            running_job_tasks[str(current_job.id)] = task

            # Wait for the job to complete before processing the next one
            try:
                await task
            except Exception as e:
                logger.error(f'Error executing job {current_job.id}: {str(e)}')

            # Remove the job from running_job_tasks
            if str(current_job.id) in running_job_tasks:
                del running_job_tasks[str(current_job.id)]

    logger.info('Job queue processor stopped')


async def process_next_job():
    """Start processing the next job in the queue if available."""
    global job_processor_task

    # Log the current state of the job processor task
    processor_status = (
        'None'
        if job_processor_task is None
        else ('Done' if job_processor_task.done() else 'Running')
    )
    logger.info(
        f'process_next_job called - job_processor_task status: {processor_status}, queue size: {len(job_queue)}'
    )

    async with job_queue_lock:
        # Only start a new processor if there are jobs in the queue and no active processor task
        if job_queue and (job_processor_task is None or job_processor_task.done()):
            # Create a new job processor task before releasing the lock
            job_processor_task = asyncio.create_task(process_job_queue())
            logger.info('Started processing next job in queue')
        else:
            await asyncio.sleep(60)
            if not job_queue:
                logger.info('Not starting job processor - queue is empty')
            elif job_processor_task is not None and not job_processor_task.done():
                logger.info(
                    'Not starting job processor - existing processor is still running'
                )


async def enqueue_job(job_obj: Job):
    """
    Updates a job's status to QUEUED, adds it to the in-memory queue,
    logs the event, and ensures the job processor task is running.

    Args:
        job_obj: The Job Pydantic model instance to enqueue.
                 Its status will be updated to QUEUED if not already.
    """
    # 1. Update status in DB first
    try:
        db.update_job_status(job_obj.id, JobStatus.QUEUED)
        logger.info(f'Job {job_obj.id} status updated to QUEUED in database.')
        # Update the local object's status as well
        job_obj.status = JobStatus.QUEUED
    except Exception as e:
        logger.error(
            f'Failed to update job {job_obj.id} status to QUEUED in DB: {e}',
            exc_info=True,
        )
        # Raise an exception to prevent potentially queueing a job
        # whose status couldn't be persisted.
        raise RuntimeError(
            f'Failed to update job {job_obj.id} status before queueing'
        ) from e

    # 2. Add to queue and manage processor
    async with job_queue_lock:
        # Safety check: Avoid adding the same job twice
        if any(j.id == job_obj.id for j in job_queue):
            logger.warning(
                f'Job {job_obj.id} is already in the queue. Skipping addition.'
            )
            return  # Job already enqueued, nothing more to do

        # Add job to the queue
        job_queue.append(job_obj)
        # Add a standard log entry
        log_message = 'Job added to queue'  # Use the consistent message
        add_job_log(str(job_obj.id), 'system', log_message)
        logger.info(f"Job {job_obj.id} added to queue. Log message: '{log_message}'")

        # Ensure the job processor task is running
        global job_processor_task
        processor_status = (
            'None'
            if job_processor_task is None
            else ('Done' if job_processor_task.done() else 'Running')
        )
        logger.info(
            f'Enqueued job {job_obj.id} - Processor status: {processor_status}, Queue size: {len(job_queue)}'
        )

        if job_processor_task is None or job_processor_task.done():
            logger.info(f'Starting job processor task after enqueuing job {job_obj.id}')
            job_processor_task = asyncio.create_task(process_job_queue())
            logger.info('Started job queue processor task.')
        else:
            logger.info(
                f'Job processor task is already running. Queue size: {len(job_queue)}'
            )
