"""
Job execution callback utilities.
"""

import asyncio
import logging
from datetime import datetime
from typing import List

import httpx

from server.utils.job_logging import add_job_log

logger = logging.getLogger(__name__)

# Constants
TOKEN_LIMIT = 200000  # Maximum number of tokens (input + output) allowed per job


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


def _create_output_callback(job_id_str: str, tenant_schema: str):
    """Creates the callback function for handling message output."""

    def output_callback(content_block):
        add_job_log(job_id_str, 'message', content_block, tenant_schema)

    return output_callback
