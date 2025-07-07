"""
Agentic sampling loop that calls the Anthropic API and local implementation of anthropic-defined computer use tools.
"""

import asyncio
import json
from typing import Any, Callable, Optional, cast
from uuid import UUID

import httpx

# Import async clients
from anthropic import (
    APIError,
    APIResponseValidationError,
    APIStatusError,
    AsyncAnthropic,
    AsyncAnthropicBedrock,
    AsyncAnthropicVertex,
)

# Import base TextBlockParam for initial message handling
# Adjust Beta type imports to come from anthropic.types.beta
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
)

from server.computer_use.config import (
    PROMPT_CACHING_BETA_FLAG,
)
from server.models.api_provider import APIProvider
from server.computer_use.logging import logger
from server.computer_use.tools import (
    TOOL_GROUPS_BY_VERSION,
    ToolCollection,
    ToolResult,
    ToolVersion,
)
from server.computer_use.utils import (
    _beta_message_param_to_job_message_content,
    _inject_prompt_caching,
    _job_message_to_beta_message_param,
    _load_system_prompt,
    _make_api_tool_result,
    _maybe_filter_to_n_most_recent_images,
    _response_to_params,
)

# Import DatabaseService and serialization utils
from server.database.service import DatabaseService

# Import the centralized health check function
from server.settings import settings
from server.utils.docker_manager import check_target_container_health

# Initialize db service - This might cause issues if DB is not ready globally.
# Consider passing db instance instead.
db = DatabaseService()


async def sampling_loop(
    *,
    # Add job_id and db service parameters
    job_id: UUID,
    db: DatabaseService,  # Pass DB service instance
    model: str,
    provider: APIProvider,
    system_prompt_suffix: str,
    messages: list[BetaMessageParam],  # Keep for initial messages
    output_callback: Callable[[BetaContentBlockParam], None],
    tool_output_callback: Callable[[ToolResult, str], None],
    api_response_callback: Callable[
        [httpx.Request, httpx.Response | object | None, Exception | None], None
    ] = None,
    max_tokens: int = 4096,
    tool_version: ToolVersion,
    token_efficient_tools_beta: bool = False,
    api_key: str = '',
    only_n_most_recent_images: Optional[int] = None,
    session_id: Optional[str] = None,
    # Remove job_id from here as it's now a primary parameter
    # job_id: Optional[str] = None,
) -> tuple[Any, list[dict[str, Any]]]:  # Return format remains the same
    """
    Agentic sampling loop that makes API calls and handles results.
    Persists message history to the database.

    Args:
        job_id: The UUID of the job being executed.
        db: Instance of DatabaseService for DB operations.
        model: Model to use
        provider: API provider to use (see APIProvider enum)
        system_prompt_suffix: Text to append to system prompt
        messages: List of *initial/new* messages to add before starting the loop.
        output_callback: Function to call with output
        tool_output_callback: Function to call with tool result
        api_response_callback: Function to call after API response
        max_tokens: Maximum number of tokens to generate
        tool_version: Version of tools to use
        token_efficient_tools_beta: Whether to use token efficient tools
        api_key: API key to use
        only_n_most_recent_images: Only keep this many most recent images
        session_id: Session ID for the computer tool

    Returns:
        (result, exchanges): The final result and list of API exchanges
    """

    tool_group = TOOL_GROUPS_BY_VERSION[tool_version]
    tool_collection = ToolCollection(*(ToolCls() for ToolCls in tool_group.tools))

    # Use the original variable name 'system'
    system = BetaTextBlockParam(
        type='text',
        text=_load_system_prompt(system_prompt_suffix),
    )

    # Keep track of all exchanges for logging
    exchanges = []

    # Store extractions and track API completion
    extractions = []
    is_completed = False

    current_sequence = db.get_next_message_sequence(job_id)
    initial_messages_to_add = messages  # Use the passed messages argument

    for init_message in initial_messages_to_add:
        serialized_content = _beta_message_param_to_job_message_content(init_message)
        db.add_job_message(
            job_id=job_id,
            sequence=current_sequence,
            role=init_message.get('role'),
            content=serialized_content,
        )
        logger.info(f'Added initial message seq {current_sequence} for job {job_id}')
        current_sequence += 1

    # TODO: Split up this very long loop into smaller functions
    while True:
        # --- Fetch current history from DB --- START
        try:
            db_messages = db.get_job_messages(job_id)
            current_messages_for_api = [
                _job_message_to_beta_message_param(msg) for msg in db_messages
            ]
            # Calculate next sequence based on fetched history
            next_sequence = (db_messages[-1]['sequence'] + 1) if db_messages else 1
        except Exception as e:
            logger.error(
                f'Failed to fetch or deserialize messages for job {job_id}: {e}',
                exc_info=True,
            )
            # Cannot continue without message history
            raise ValueError(f'Failed to load message history for job {job_id}') from e
        # --- Fetch current history from DB --- END

        enable_prompt_caching = False
        betas = [tool_group.beta_flag] if tool_group.beta_flag else []
        if token_efficient_tools_beta:
            betas.append('token-efficient-tools-2025-02-19')
        image_truncation_threshold = 1
        # --- Client Initialization (remains the same) ---
        # TODO: Does this need to be done for every iteration?
        if provider == APIProvider.ANTHROPIC:
            # Use AsyncAnthropic instead of Anthropic
            client = AsyncAnthropic(api_key=api_key, max_retries=4)
            enable_prompt_caching = True
        elif provider == APIProvider.VERTEX:
            # Use AsyncAnthropicVertex instead of AnthropicVertex
            client = AsyncAnthropicVertex()
        elif provider == APIProvider.BEDROCK:
            # AWS credentials should be set in environment variables
            # by the server.py initialization
            aws_region = settings.AWS_REGION
            aws_access_key = settings.AWS_ACCESS_KEY_ID
            aws_secret_key = settings.AWS_SECRET_ACCESS_KEY
            aws_session_token = settings.AWS_SESSION_TOKEN

            # Initialize with available credentials
            bedrock_kwargs = {'aws_region': aws_region}
            if aws_access_key and aws_secret_key:
                bedrock_kwargs['aws_access_key'] = aws_access_key
                bedrock_kwargs['aws_secret_key'] = aws_secret_key
                if aws_session_token:
                    bedrock_kwargs['aws_session_token'] = aws_session_token

            # Use AsyncAnthropicBedrock instead of AnthropicBedrock
            client = AsyncAnthropicBedrock(**bedrock_kwargs)
            logger.info(f'Using AsyncAnthropicBedrock client with region: {aws_region}')

        if enable_prompt_caching:
            betas.append(PROMPT_CACHING_BETA_FLAG)
            _inject_prompt_caching(
                current_messages_for_api
            )  # Inject into current history
            # only_n_most_recent_images = 0
            system['cache_control'] = {'type': 'ephemeral'}
        # No need for else block or system_block variable

        if only_n_most_recent_images:
            _maybe_filter_to_n_most_recent_images(
                current_messages_for_api,  # Filter current history
                only_n_most_recent_images,
                min_removal_threshold=image_truncation_threshold,
            )

        # Check for cancellation before API call
        try:
            await asyncio.sleep(0)
            # If we get here, the task hasn't been cancelled
        except asyncio.CancelledError:
            logger.info('Sampling loop cancelled before API call')
            raise

        try:
            # Use original 'system' variable
            raw_response = await client.beta.messages.with_raw_response.create(
                max_tokens=max_tokens,
                messages=current_messages_for_api,
                model=model,
                system=[system],  # Pass original system dict
                tools=tool_collection.to_params(),
                betas=betas,
            )

            if api_response_callback:
                api_response_callback(
                    raw_response.http_response.request, raw_response.http_response, None
                )

            # Add exchange to the list
            exchanges.append(
                {
                    'request': raw_response.http_response.request,
                    'response': raw_response.http_response,
                }
            )

        except (APIStatusError, APIResponseValidationError) as e:
            # For other API errors, handle as before
            if api_response_callback:
                api_response_callback(e.request, e.response, e)
            raise ValueError('API call failed with error') from e

        except APIError as e:
            if api_response_callback:
                api_response_callback(e.request, e.body, e)
            # Return extractions if we have them, otherwise raise an error
            raise ValueError('API call failed with error') from e

        except asyncio.CancelledError:
            logger.info('API call cancelled')
            raise

        # Check for cancellation after API call
        try:
            # Use asyncio.sleep(0) to allow cancellation to be processed
            await asyncio.sleep(0)
            # If we get here, the task hasn't been cancelled
        except asyncio.CancelledError:
            logger.info('Sampling loop cancelled after API call')
            raise

        response = raw_response.parse()
        response_params = _response_to_params(response)

        # --- Save Assistant Message to DB --- START
        try:
            resulting_message = BetaMessageParam(
                content=response_params, role='assistant'
            )
            serialized_message = _beta_message_param_to_job_message_content(
                resulting_message
            )
            db.add_job_message(
                job_id=job_id,
                sequence=next_sequence,
                role=resulting_message[
                    'role'
                ],  # Tool results are sent back as user role
                content=serialized_message,
            )
            logger.info(f'Saved assistant message seq {next_sequence} for job {job_id}')
            next_sequence += 1  # Increment sequence for potential tool results
        except Exception as e:
            logger.error(
                f'Failed to save assistant message for job {job_id}: {e}', exc_info=True
            )
            # Decide how to proceed. Maybe raise, maybe just log and continue?
            # Raising error for now as history persistence failed.
            raise ValueError(
                f'Failed to save assistant message history for job {job_id}'
            ) from e
        # --- Save Assistant Message to DB --- END

        # Check if the model ended its turn
        is_completed = response.stop_reason == 'end_turn'
        logger.info(
            f'API response stop_reason: {response.stop_reason}, is_completed: {is_completed}'
        )

        found_tool_use = False
        for content_block in response_params:
            output_callback(content_block)
            if content_block['type'] == 'tool_use':
                found_tool_use = True

                # --- Target Health Check --- START
                health_check_ok = False
                health_check_reason = (
                    'Health check prerequisites not met (session_id missing).'
                )
                if session_id:
                    try:
                        session_details = db.get_session(UUID(session_id))
                        if session_details and session_details.get('container_ip'):
                            container_ip = session_details['container_ip']
                            health_status = await check_target_container_health(
                                container_ip
                            )
                            health_check_ok = health_status['healthy']
                            health_check_reason = health_status['reason']
                        else:
                            health_check_reason = f'Could not retrieve container_ip for session {session_id}.'
                            logger.warning(f'Job {job_id}: {health_check_reason}')
                    except Exception as e:
                        health_check_reason = f'Error retrieving session details for health check: {str(e)}'
                        logger.error(f'Job {job_id}: {health_check_reason}')
                else:
                    logger.warning(
                        f'Job {job_id}: Cannot perform health check, session_id is missing.'
                    )

                if not health_check_ok:
                    # REMOVE DB update, just return the specific dict
                    # db.update_job_status(job_id, "paused") # REMOVED
                    logger.warning(
                        f'Job {job_id}: Target health check failed: {health_check_reason}'
                    )
                    return {
                        'success': False,  # Keep success=False marker
                        'error': 'Target Health Check Failed',
                        'error_description': health_check_reason,
                    }, exchanges
                # --- Target Health Check --- END

                result = await tool_collection.run(
                    name=content_block['name'],
                    tool_input=cast(dict[str, Any], content_block['input']),
                    session_id=session_id,
                )

                # --- Save Tool Result Message to DB --- START
                try:
                    tool_result_block = _make_api_tool_result(
                        result, content_block['id']
                    )
                    resulting_message = BetaMessageParam(
                        content=[tool_result_block], role='user'
                    )
                    serialized_message = _beta_message_param_to_job_message_content(
                        resulting_message
                    )
                    db.add_job_message(
                        job_id=job_id,
                        sequence=next_sequence,
                        role=resulting_message[
                            'role'
                        ],  # Tool results are sent back as user role
                        content=serialized_message,
                    )
                    logger.info(
                        f'Saved tool result message seq {next_sequence} for tool {content_block["name"]} job {job_id}'
                    )
                    next_sequence += 1  # Increment sequence for next potential message
                except Exception as e:
                    logger.error(
                        f'Failed to save tool result message for job {job_id}: {e}',
                        exc_info=True,
                    )
                    raise ValueError(
                        f'Failed to save tool result history for job {job_id}'
                    ) from e
                # --- Save Tool Result Message to DB --- END

                # Special handling for UI not as expected tool
                if content_block['name'] == 'ui_not_as_expected':
                    reasoning = result.output
                    # REMOVE DB update, just return the specific dict
                    # db.update_job_status(job_id, "paused") # REMOVED
                    logger.warning(f'Job {job_id}: UI Mismatch Detected: {reasoning}')
                    return {
                        'success': False,  # Keep success=False marker
                        'error': 'UI Mismatch Detected',
                        'error_description': reasoning,
                    }, exchanges

                # Handle extraction tool results
                if content_block['name'] == 'extraction':
                    logger.info(f'Processing extraction tool result: {result}')
                    if result.output:
                        try:
                            # Parse the extraction data
                            extraction_data = json.loads(result.output)
                            logger.info(
                                f'Successfully parsed extraction data: {extraction_data}'
                            )

                            # Store only the result field from the extraction data
                            if (
                                isinstance(extraction_data, dict)
                                and 'result' in extraction_data
                            ):
                                extractions.append(extraction_data['result'])
                            else:
                                extractions.append(extraction_data)
                            logger.info(
                                f'Added extraction data: {extraction_data} (total: {len(extractions)})'
                            )
                        except json.JSONDecodeError as e:
                            logger.error(f'Failed to parse extraction result: {e}')

                tool_output_callback(result, content_block['id'])

        # Check if loop should terminate
        if not found_tool_use:
            if is_completed:
                logger.info(
                    f'Model ended turn with {len(extractions)} extractions and no further tool use.'
                )
                if extractions:
                    # Loop finished successfully with extraction, return the result.
                    # Status update will be handled by the caller.
                    return extractions[-1], exchanges
                else:
                    # Loop finished but no extraction - this is an error condition.
                    # Raise exception, status update handled by caller's except block.
                    logger.error(
                        f'Job {job_id}: Model ended turn without providing required extraction.'
                    )
                    raise ValueError(
                        'Model ended its turn without providing any extractions'
                    )
            else:
                # Model has more to say (e.g., text response without tool use), continue loop.
                continue
        # else: If tools were used, the loop automatically continues.

        # Check for cancellation before potential next iteration
        try:
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            logger.info('Sampling loop cancelled at end of loop iteration')
            raise

    # Code should not typically reach here unless loop is broken unexpectedly.
    # Let caller handle this via timeout or other means.
    logger.warning(
        f'Sampling loop for job {job_id} exited unexpectedly without reaching a defined end state.'
    )
    # Raise an error to indicate unexpected exit.
    raise RuntimeError('Sampling loop exited unexpectedly')
