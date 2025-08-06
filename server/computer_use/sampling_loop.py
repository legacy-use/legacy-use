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

from server.computer_use.client import LegacyUseClient
from server.computer_use.config import (
    PROMPT_CACHING_BETA_FLAG,
    APIProvider,
)
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


# TODO: Move helper functions to a separate file
# Helper functions for the sampling loop
async def _fetch_message_history(
    db: DatabaseService, job_id: UUID
) -> tuple[list[BetaMessageParam], int]:
    """
    Fetch current message history from the database.

    Returns:
        Tuple of (messages for API, next sequence number)
    """
    try:
        db_messages = db.get_job_messages(job_id)
        current_messages_for_api = [
            _job_message_to_beta_message_param(msg) for msg in db_messages
        ]
        # Calculate next sequence based on fetched history
        next_sequence = (db_messages[-1]['sequence'] + 1) if db_messages else 1
        return current_messages_for_api, next_sequence
    except Exception as e:
        logger.error(
            f'Failed to fetch or deserialize messages for job {job_id}: {e}',
            exc_info=True,
        )
        # Cannot continue without message history
        raise ValueError(f'Failed to load message history for job {job_id}') from e


def _initialize_api_client(
    provider: APIProvider,
    api_key: str,
    tool_version: ToolVersion,
    token_efficient_tools_beta: bool,
) -> tuple[Any, list[str], bool, int]:
    """
    Initialize the appropriate API client based on provider.

    Returns:
        Tuple of (client, betas list, enable_prompt_caching, image_truncation_threshold)
    """
    tool_group = TOOL_GROUPS_BY_VERSION[tool_version]
    enable_prompt_caching = False
    betas = [tool_group.beta_flag] if tool_group.beta_flag else []
    if token_efficient_tools_beta:
        betas.append('token-efficient-tools-2025-02-19')
    image_truncation_threshold = 1

    # reload pydantic variables
    settings.__init__()

    if provider == APIProvider.ANTHROPIC:
        client = AsyncAnthropic(api_key=api_key, max_retries=4)
        enable_prompt_caching = True
    elif provider == APIProvider.VERTEX:
        client = AsyncAnthropicVertex()
    elif provider == APIProvider.BEDROCK:
        # AWS credentials should be set in environment variables
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

        client = AsyncAnthropicBedrock(**bedrock_kwargs)
        logger.info(f'Using AsyncAnthropicBedrock client with region: {aws_region}')
    elif provider == APIProvider.LEGACYUSE_PROXY:
        client = LegacyUseClient(api_key=settings.LEGACYUSE_PROXY_API_KEY)
    else:
        raise ValueError(f'Unknown provider: {provider}')

    if enable_prompt_caching:
        betas.append(PROMPT_CACHING_BETA_FLAG)

    return client, betas, enable_prompt_caching, image_truncation_threshold


def _prepare_api_messages(
    messages: list[BetaMessageParam],
    system: BetaTextBlockParam,
    enable_prompt_caching: bool,
    only_n_most_recent_images: Optional[int],
    image_truncation_threshold: int,
) -> None:
    """
    Prepare messages for API call (inject caching, filter images).
    Modifies messages and system in-place.
    """
    if enable_prompt_caching:
        _inject_prompt_caching(messages)
        system['cache_control'] = {'type': 'ephemeral'}

    if only_n_most_recent_images:
        _maybe_filter_to_n_most_recent_images(
            messages,
            only_n_most_recent_images,
            min_removal_threshold=image_truncation_threshold,
        )


async def _check_cancellation(context: str) -> None:
    """Check if the task has been cancelled."""
    try:
        await asyncio.sleep(0)
    except asyncio.CancelledError:
        logger.info(f'Sampling loop cancelled {context}')
        raise


async def _make_api_call(
    client: Any,
    max_tokens: int,
    messages: list[BetaMessageParam],
    model: str,
    system: BetaTextBlockParam,
    tool_collection: ToolCollection,
    betas: list[str],
    api_response_callback: Optional[Callable],
    job_id: UUID,
) -> tuple[Any, dict[str, Any]]:
    """
    Make the API call and handle responses.

    Returns:
        Tuple of (response, exchange dict)
    """
    try:
        raw_response = await client.beta.messages.with_raw_response.create(
            max_tokens=max_tokens,
            messages=messages,
            model=model,
            system=[system],
            tools=tool_collection.to_params(),
            betas=betas,
            temperature=0.0,
        )

        if api_response_callback:
            api_response_callback(
                raw_response.http_response.request, raw_response.http_response, None
            )

        exchange = {
            'request': raw_response.http_response.request,
            'response': raw_response.http_response,
        }

        return raw_response.parse(), exchange

    except (APIStatusError, APIResponseValidationError) as e:
        if e.response.status_code == 403 and 'API Credits Exceeded' in str(e):
            logger.error(f'Job {job_id}: API Credits Exceeded')
            raise APIError(
                message='API Credits Exceeded', request=e.request, body=str(e)
            )
        # For other API errors, handle as before
        if api_response_callback:
            api_response_callback(e.request, e.response, e)
        logger.error(f'Job {job_id}: API call failed with error: {e.message}')
        raise ValueError(e.message) from e

    except APIError as e:
        if api_response_callback:
            api_response_callback(e.request, e.body, e)
        raise ValueError(e.message) from e


def _save_message_to_db(
    db: DatabaseService,
    job_id: UUID,
    sequence: int,
    message: BetaMessageParam,
    message_type: str,
) -> None:
    """Save a message to the database."""
    try:
        serialized_message = _beta_message_param_to_job_message_content(message)
        db.add_job_message(
            job_id=job_id,
            sequence=sequence,
            role=message['role'],
            content=serialized_message,
        )
        logger.info(f'Saved {message_type} message seq {sequence} for job {job_id}')
    except Exception as e:
        logger.error(
            f'Failed to save {message_type} message for job {job_id}: {e}',
            exc_info=True,
        )
        raise ValueError(
            f'Failed to save {message_type} message history for job {job_id}'
        ) from e


async def _perform_health_check(
    db: DatabaseService,
    session_id: Optional[str],
    job_id: UUID,
) -> tuple[bool, str]:
    """
    Perform health check on target container.

    Returns:
        Tuple of (is_healthy, reason)
    """
    if not session_id:
        reason = 'Health check prerequisites not met (session_id missing).'
        logger.warning(
            f'Job {job_id}: Cannot perform health check, session_id is missing.'
        )
        return False, reason

    try:
        session_details = db.get_session(UUID(session_id))
        if session_details and session_details.get('container_ip'):
            container_ip = session_details['container_ip']
            health_status = await check_target_container_health(container_ip)
            return health_status['healthy'], health_status['reason']
        else:
            reason = f'Could not retrieve container_ip for session {session_id}.'
            logger.warning(f'Job {job_id}: {reason}')
            return False, reason
    except Exception as e:
        reason = f'Error retrieving session details for health check: {str(e)}'
        logger.error(f'Job {job_id}: {reason}')
        return False, reason


async def _process_tool_use(
    content_block: dict[str, Any],
    tool_collection: ToolCollection,
    session_id: Optional[str],
    db: DatabaseService,
    job_id: UUID,
    next_sequence: int,
    tool_output_callback: Callable,
    extractions: list[Any],
    exchanges: list[dict[str, Any]],
) -> tuple[Optional[dict], int]:
    """
    Process a tool use block.

    Returns:
        Tuple of (error_result or None, updated next_sequence)
    """
    # Perform health check
    health_check_ok, health_check_reason = await _perform_health_check(
        db, session_id, job_id
    )

    if not health_check_ok:
        logger.warning(
            f'Job {job_id}: Target health check failed: {health_check_reason}'
        )
        return {
            'success': False,
            'error': 'Target Health Check Failed',
            'error_description': health_check_reason,
        }, next_sequence

    # Execute tool
    result = await tool_collection.run(
        name=content_block['name'],
        tool_input=cast(dict[str, Any], content_block['input']),
        session_id=session_id,
    )

    # Save tool result to DB
    tool_result_block = _make_api_tool_result(result, content_block['id'])
    resulting_message = BetaMessageParam(content=[tool_result_block], role='user')
    _save_message_to_db(db, job_id, next_sequence, resulting_message, 'tool result')
    next_sequence += 1

    # Handle special tool cases
    if content_block['name'] == 'ui_not_as_expected':
        reasoning = result.output
        logger.warning(f'Job {job_id}: UI Mismatch Detected: {reasoning}')
        return {
            'success': False,
            'error': 'UI Mismatch Detected',
            'error_description': reasoning,
        }, next_sequence

    # Handle extraction tool results
    if content_block['name'] == 'extraction':
        logger.info(f'Processing extraction tool result: {result}')
        if result.output:
            try:
                extraction_data = json.loads(result.output)
                logger.info(f'Successfully parsed extraction data: {extraction_data}')

                # Store only the result field from the extraction data
                if isinstance(extraction_data, dict) and 'result' in extraction_data:
                    extractions.append(extraction_data['result'])
                else:
                    extractions.append(extraction_data)
                logger.info(
                    f'Added extraction data: {extraction_data} (total: {len(extractions)})'
                )
            except json.JSONDecodeError as e:
                logger.error(f'Failed to parse extraction result: {e}')

    tool_output_callback(result, content_block['id'])
    return None, next_sequence


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
    # Initialize tool collection
    tool_group = TOOL_GROUPS_BY_VERSION[tool_version]
    tool_collection = ToolCollection(*(ToolCls() for ToolCls in tool_group.tools))

    # Create system prompt
    system = BetaTextBlockParam(
        type='text',
        text=_load_system_prompt(system_prompt_suffix),
    )

    # Initialize tracking variables
    exchanges = []
    extractions = []

    # Add initial messages to database
    current_sequence = db.get_next_message_sequence(job_id)
    for init_message in messages:
        serialized_content = _beta_message_param_to_job_message_content(init_message)
        db.add_job_message(
            job_id=job_id,
            sequence=current_sequence,
            role=init_message.get('role'),
            content=serialized_content,
        )
        logger.info(f'Added initial message seq {current_sequence} for job {job_id}')
        current_sequence += 1

    # Main processing loop
    while True:
        # Fetch current message history
        current_messages_for_api, next_sequence = await _fetch_message_history(
            db, job_id
        )

        # Initialize API client (TODO: Consider caching this between iterations)
        client, betas, enable_prompt_caching, image_truncation_threshold = (
            _initialize_api_client(
                provider, api_key, tool_version, token_efficient_tools_beta
            )
        )

        # Prepare messages for API call
        _prepare_api_messages(
            current_messages_for_api,
            system,
            enable_prompt_caching,
            only_n_most_recent_images,
            image_truncation_threshold,
        )

        # Check for cancellation before API call
        await _check_cancellation('before API call')

        # Make API call
        try:
            response, exchange = await _make_api_call(
                client,
                max_tokens,
                current_messages_for_api,
                model,
                system,
                tool_collection,
                betas,
                api_response_callback,
                job_id,
            )
            exchanges.append(exchange)
        except APIError as e:
            # Handle special case of API Credits Exceeded
            if 'API Credits Exceeded' in str(e):
                return {
                    'success': False,
                    'error': 'API Credits Exceeded',
                    'error_description': str(e),
                }, exchanges
            raise

        # Check for cancellation after API call
        await _check_cancellation('after API call')

        # Process response
        response_params = _response_to_params(response)

        # Save assistant message to database
        assistant_message = BetaMessageParam(content=response_params, role='assistant')
        _save_message_to_db(db, job_id, next_sequence, assistant_message, 'assistant')
        next_sequence += 1

        # Check if the model ended its turn
        is_completed = response.stop_reason == 'end_turn'
        logger.info(
            f'API response stop_reason: {response.stop_reason}, is_completed: {is_completed}'
        )

        # Process response content blocks
        found_tool_use = False
        for content_block in response_params:
            output_callback(content_block)

            if content_block['type'] == 'tool_use':
                found_tool_use = True

                # Process tool use
                error_result, next_sequence = await _process_tool_use(
                    content_block,
                    tool_collection,
                    session_id,
                    db,
                    job_id,
                    next_sequence,
                    tool_output_callback,
                    extractions,
                    exchanges,
                )

                # Return early if there was an error
                if error_result:
                    return error_result, exchanges

        # Check loop termination conditions
        if not found_tool_use:
            if is_completed:
                logger.info(
                    f'Model ended turn with {len(extractions)} extractions and no further tool use.'
                )
                if extractions:
                    # Loop finished successfully with extraction
                    return extractions[-1], exchanges
                else:
                    # Loop finished but no extraction - error condition
                    logger.error(
                        f'Job {job_id}: Model ended turn without providing required extraction.'
                    )
                    raise ValueError(
                        'Model ended its turn without providing any extractions'
                    )
            else:
                # Model has more to say, continue loop
                logger.info(f'Job {job_id}: Model has more to say, continuing loop')
                continue

        # Check for cancellation before next iteration
        await _check_cancellation('at end of loop iteration')

    # Should not reach here under normal circumstances
    logger.warning(
        f'Sampling loop for job {job_id} exited unexpectedly without reaching a defined end state.'
    )
    raise RuntimeError('Sampling loop exited unexpectedly')
