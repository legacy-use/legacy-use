"""
Job execution logic with Hatchet integration.

This module provides functions for executing jobs using Hatchet for queue management
while preserving the important logic from the original job execution system.

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
from datetime import datetime
from typing import Any, List

import httpx

from server.models.base import Job, JobStatus
from server.utils.db_dependencies import TenantAwareDatabaseService
from server.utils.telemetry import capture_job_resolved
from server.utils.hatchet_client import hatchet_job_manager

# Set up logging
logger = logging.getLogger(__name__)

# Constants
TOKEN_LIMIT = 200000  # Maximum number of tokens (input + output) allowed per job

# Dictionary to store running job tasks (now managed by Hatchet)
running_job_tasks = {}


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
                            if current_total > TOKEN_LIMIT:
                                # Add warning about token limit
                                limit_message = f'Token usage limit of {TOKEN_LIMIT} exceeded. Current usage: {current_total}. Job will be interrupted.'
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


# Main job execution logic - adapted for Hatchet
async def execute_api_in_background_with_tenant(job: Job, tenant_schema: str):
    """Execute a job's API call in the background using Hatchet."""
    from server.core import APIGatewayCore
    from server.database.multi_tenancy import with_db

    job_id_str = str(job.id)

    # Track token usage for this job - Use a list to allow modification by nonlocal callback
    running_token_total_ref = [0]

    # Add initial job log
    add_job_log(job_id_str, 'system', 'Hatchet picked up job', tenant_schema)

    try:
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
            if running_token_total > TOKEN_LIMIT:
                error_message = f'Job was automatically terminated: exceeded token limit of {TOKEN_LIMIT} tokens (used {running_token_total} tokens)'
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
                        if running_token_total > TOKEN_LIMIT
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
        if running_token_total > TOKEN_LIMIT:
            add_job_log(
                job_id_str,
                'system',
                f'Job execution was cancelled due to token limit ({running_token_total}/{TOKEN_LIMIT})',
                tenant_schema,
            )
        else:
            add_job_log(
                job_id_str, 'system', 'Job execution was cancelled', tenant_schema
            )

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


# Hatchet integration functions
async def initialize_job_queue():
    """Initialize job queues - now handled by Hatchet."""
    logger.info('Job queue initialization now handled by Hatchet')
    # Hatchet handles queue initialization automatically
    pass


async def initialize_job_queue_for_tenant(tenant_schema: str):
    """Initialize job queue for a specific tenant - now handled by Hatchet."""
    logger.info(
        f'Job queue initialization for tenant {tenant_schema} now handled by Hatchet'
    )
    # Hatchet handles per-tenant queuing automatically
    pass


async def start_job_processor_for_tenant(tenant_schema: str):
    """Start job processor for a specific tenant - now handled by Hatchet workers."""
    logger.info(
        f'Job processor for tenant {tenant_schema} now handled by Hatchet workers'
    )
    # Hatchet workers handle job processing automatically
    pass


async def process_job_queue_for_tenant(tenant_schema: str):
    """Process jobs for a specific tenant - deprecated in favor of Hatchet."""
    logger.warning('process_job_queue_for_tenant is deprecated - using Hatchet workers')
    raise NotImplementedError('Use Hatchet workers for job processing')


async def process_job_with_tenant(job: Job, tenant_schema: str):
    """Process a job using tenant-aware database service - deprecated."""
    logger.warning('process_job_with_tenant is deprecated - using Hatchet workflows')
    raise NotImplementedError('Use Hatchet workflows for job processing')


# Export the function to be used in the main FastAPI app startup
job_queue_initializer = initialize_job_queue


async def enqueue_job(job_obj: Job, tenant_schema: str):
    """
    Enqueue a job for execution via Hatchet.

    This function maintains the same interface as the original enqueue_job
    but uses Hatchet for job queuing and execution.

    Args:
        job_obj: The Job Pydantic model instance to enqueue.
        tenant_schema: The tenant schema for this job.
    """
    try:
        logger.info(
            f'Enqueuing job {job_obj.id} for tenant {tenant_schema} via Hatchet'
        )

        # Use Hatchet to enqueue the job
        workflow_run_id = await hatchet_job_manager.enqueue_job(job_obj, tenant_schema)

        # Store the workflow run ID for tracking if needed
        running_job_tasks[str(job_obj.id)] = {
            'workflow_run_id': workflow_run_id,
            'tenant_schema': tenant_schema,
            'status': 'queued',
        }

        logger.info(
            f'Job {job_obj.id} successfully enqueued in Hatchet with run ID: {workflow_run_id}'
        )

    except Exception as e:
        logger.error(f'Failed to enqueue job {job_obj.id} via Hatchet: {str(e)}')
        raise


# Keep these functions for compatibility but mark as deprecated
async def process_job_queue():
    """Deprecated: This function is no longer used. Use Hatchet workers."""
    logger.warning('process_job_queue is deprecated - use Hatchet workers')
    raise NotImplementedError('Use Hatchet workers')


async def process_next_job():
    """Deprecated: This function is no longer used. Use Hatchet workers."""
    logger.warning('process_next_job is deprecated - use Hatchet workers')
    raise NotImplementedError('Use Hatchet workers')
