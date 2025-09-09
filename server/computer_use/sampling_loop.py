"""
Agentic sampling loop that calls the Anthropic API and local implementation of anthropic-defined computer use tools.
"""

import asyncio
import json
from typing import Any, Callable, Optional, cast
from uuid import UUID

import httpx

# Import API exception types for error handling
from anthropic import (
    APIError,
    APIResponseValidationError,
    APIStatusError,
)

# Import base TextBlockParam for initial message handling
# Adjust Beta type imports to come from anthropic.types.beta
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
)

from server.computer_use.config import APIProvider
from server.computer_use.handlers.registry import get_handler
from server.computer_use.logging import logger
from server.computer_use.state_utils import check_and_compare_state
from server.computer_use.tools import (
    TOOL_GROUPS_BY_VERSION,
    ToolCollection,
    ToolResult,
    ToolVersion,
)
from server.computer_use.tools.custom_action import CustomActionTool
from server.computer_use.utils import (
    _beta_message_param_to_job_message_content,
    _job_message_to_beta_message_param,
    _load_system_prompt,
    _make_api_tool_result,
)

# Import DatabaseService and serialization utils
from server.database.service import DatabaseService

# Import the centralized health check function
from server.utils.docker_manager import check_target_container_health

ApiResponseCallback = Callable[
    [httpx.Request, httpx.Response | object | None, Exception | None], None
]


async def sampling_loop(
    *,
    # Add job_id and db service parameters
    job_id: UUID,
    db_tenant: DatabaseService,  # Pass DB service instance
    model: str,
    provider: APIProvider,
    system_prompt_suffix: str,
    messages: list[BetaMessageParam],  # Keep for initial messages
    output_callback: Callable[[BetaContentBlockParam], None],
    tool_output_callback: Callable[[ToolResult, str], None],
    api_response_callback: Optional[ApiResponseCallback] = None,
    max_tokens: int = 4096,
    tool_version: ToolVersion,
    token_efficient_tools_beta: bool = False,
    api_key: str = '',
    only_n_most_recent_images: Optional[int] = None,
    session_id: str,
    tenant_schema: str,
    job_data: dict[str, Any],
    allow_state_based_tool_use: bool = True,
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

    # Create tools (no longer need database service)
    tools = []
    for ToolCls in tool_group.tools:
        if ToolCls == CustomActionTool:
            # get api_def specific custom actions
            custom_actions = db_tenant.get_custom_actions(
                job_data['api_definition_version_id'],
            )
            tools.append(ToolCls(custom_actions, job_data['parameters']))
        else:
            tools.append(ToolCls())

    tool_collection = ToolCollection(*tools)

    # Initialize handler for the provider
    handler = get_handler(
        provider=provider,
        model=model,
        tool_beta_flag=tool_group.beta_flag,
        token_efficient_tools_beta=token_efficient_tools_beta,
        only_n_most_recent_images=only_n_most_recent_images,
        tenant_schema=tenant_schema,
    )

    # Load system prompt
    system_prompt = _load_system_prompt(system_prompt_suffix)

    # Keep track of all exchanges for logging
    exchanges = []

    # Store extractions and track API completion
    extractions = []
    is_completed = False

    current_sequence = db_tenant.get_next_message_sequence(job_id)
    initial_messages_to_add = messages  # Use the passed messages argument

    for init_message in initial_messages_to_add:
        serialized_content = _beta_message_param_to_job_message_content(init_message)
        db_tenant.add_job_message(
            job_id=job_id,
            sequence=current_sequence,
            role=init_message.get('role'),
            content=serialized_content,
        )
        logger.info(f'Added initial message seq {current_sequence} for job {job_id}')
        current_sequence += 1

    # TODO move to a seperate function
    # get the last two jobs: TODO: think if it makes sense to have the logic adjustable, by comparing to the last "n" ideal jobs. this could be useful to increase the accuracy of the matching state
    last_two_jobs = db_tenant.get_two_ideal_jobs(job_data['api_definition_version_id'])
    print(f'Job {job_id}: Last two jobs: {last_two_jobs}')

    if len(last_two_jobs) == 2:
        tool_invocations_a = db_tenant.get_all_tool_invocations_and_results_for_job(
            last_two_jobs[0].get('id')
        )
        tool_invocations_b = db_tenant.get_all_tool_invocations_and_results_for_job(
            last_two_jobs[1].get('id')
        )
        tool_invocations_a_trimmed = [
            (t.get('log_type'), t.get('timestamp')) for t in tool_invocations_a
        ]
        tool_invocations_b_trimmed = [
            (t.get('log_type'), t.get('timestamp')) for t in tool_invocations_b
        ]
        print(
            f'Job {job_id}: Tool invocations a trimmed: {tool_invocations_a_trimmed}, tool invocations b trimmed: {tool_invocations_b_trimmed}'
        )
        print(
            f'Job {job_id}: Tool invocations a: {len(tool_invocations_a)}, tool invocations b: {len(tool_invocations_b)}'
        )
    else:
        tool_invocations_a = None
        tool_invocations_b = None
        logger.error(f'Job {job_id}: Last two jobs are not equal to 2')

    container_ip = db_tenant.get_session(session_id)['container_ip']
    tool_use_count = 0

    # TODO: Split up this very long loop into smaller functions
    while True:
        # --- Fetch current history from DB --- START
        try:
            db_messages = db_tenant.get_job_messages(job_id)
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

        # Check if we have a matching state -> tool_call, otherwise, AI

        # get the screenshot before the tool_use
        # TODO; think if we acutally need two runs
        if (
            tool_invocations_a
            and tool_invocations_b
            and tool_use_count < len(tool_invocations_a)
            and allow_state_based_tool_use
        ):
            next_tool_use, tool_use_count = await check_and_compare_state(
                tool_invocations_a, tool_invocations_b, tool_use_count, container_ip
            )
        else:
            logger.error(f'Job {job_id}: Tool invocations a or b are not given')
            next_tool_use = None

        if next_tool_use:
            logger.info(
                f'Job {job_id}: Matching state found, continuing with tool call: {next_tool_use}'
            )

            # mock response_params, stop_reason
            text_context = {
                'text': 'Automatically invoked tool call!',
                'type': 'text',
            }
            response_params = [text_context, next_tool_use]
            stop_reason = 'tool_use'

            # mock request
            request = None

            # TODO: should we mark the job as state_based_tool_use, so we don't use it for future references? Would it be a problem?

        else:
            logger.info(f'Job {job_id}: No matching state found, continuing with model')

            # --- Initialize client ---
            client = await handler.initialize_client(api_key=api_key)

            # Check for cancellation before API call
            try:
                await asyncio.sleep(0)
                # If we get here, the task hasn't been cancelled
            except asyncio.CancelledError:
                logger.info('Sampling loop cancelled before API call')
                raise

            try:
                # Make API call via handler
                (
                    response_params,
                    stop_reason,
                    request,
                    raw_response,
                ) = await handler.execute(
                    client=client,
                    messages=current_messages_for_api,  # Pass raw Anthropic format
                    system=system_prompt,  # type: ignore[arg-type]  # Pass raw string
                    tools=tool_collection,  # type: ignore[arg-type]  # Pass raw ToolCollection
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0.0,
                )

                if api_response_callback:
                    api_response_callback(request, raw_response, None)

                # Add exchange to the list
                exchanges.append(
                    {
                        'request': request,
                        'response': raw_response,
                    }
                )

            except (APIStatusError, APIResponseValidationError) as e:
                if e.response.status_code == 403 and 'API Credits Exceeded' in str(e):
                    logger.error(f'Job {job_id}: API Credits Exceeded')
                    return {
                        'success': False,
                        'error': 'API Credits Exceeded',
                        'error_description': str(e),
                    }, exchanges
                # For other API errors, handle as before
                if api_response_callback:
                    api_response_callback(e.request, e.response, e)
                logger.error(f'Job {job_id}: API call failed with error: {e.message}')
                raise ValueError(e.message) from e

            except APIError as e:
                if api_response_callback:
                    api_response_callback(e.request, e.body, e)
                # Return extractions if we have them, otherwise raise an error
                raise ValueError(e.message) from e

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

        # --- Save Assistant Message to DB --- START
        try:
            resulting_message = BetaMessageParam(
                content=response_params, role='assistant'
            )
            serialized_message = _beta_message_param_to_job_message_content(
                resulting_message
            )
            db_tenant.add_job_message(
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
        is_completed = stop_reason == 'end_turn'
        logger.info(
            f'API response stop_reason: {stop_reason}, is_completed: {is_completed}'
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
                        # Validate session_id is a valid UUID
                        if not session_id or not isinstance(session_id, str):
                            health_check_reason = (
                                f'Invalid session_id format: {session_id}'
                            )
                            logger.warning(f'Job {job_id}: {health_check_reason}')
                        else:
                            session_details = db_tenant.get_session(UUID(session_id))
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
                    except ValueError:
                        health_check_reason = f'Invalid session_id format: {session_id}'
                        logger.error(f'Job {job_id}: {health_check_reason}')
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

                # Get session object for computer tools
                session_obj = None
                if session_id:
                    try:
                        # Validate session_id is a valid UUID
                        if session_id and isinstance(session_id, str):
                            session_obj = db_tenant.get_session(UUID(session_id))
                        else:
                            logger.warning(f'Invalid session_id format: {session_id}')
                    except ValueError:
                        logger.warning(f'Invalid session_id format: {session_id}')
                    except Exception as e:
                        logger.warning(f'Could not retrieve session {session_id}: {e}')

                result = await tool_collection.run(
                    name=content_block['name'],
                    tool_input=cast(dict[str, Any], content_block['input']),
                    session_id=session_id,
                    session=session_obj,
                )

                tool_use_count += 2  # 2, because we have request and response # TODO: just multiple by two when forwarding

                # --- Save Tool Result Message to DB --- START
                try:
                    # TODO: Remove this as this shouldn't be model dependent
                    tool_result_block = _make_api_tool_result(
                        result, content_block['id']
                    )
                    resulting_message = BetaMessageParam(
                        content=[tool_result_block], role='user'
                    )
                    serialized_message = _beta_message_param_to_job_message_content(
                        resulting_message
                    )
                    db_tenant.add_job_message(
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
        # Special case: If extraction tool was called and model wants to end, terminate immediately
        is_extraction_tool_called = any(
            block.get('name') == 'extraction'
            for block in response_params
            if block.get('type') == 'tool_use'
        )

        if is_extraction_tool_called and is_completed and extractions:
            logger.info(
                f'Model called extraction tool and ended turn with {len(extractions)} extractions.'
            )
            return extractions[-1], exchanges

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
                logger.info(f'Job {job_id}: Model has more to say, continuing loop')
                continue
        # else: If tools were used (other than extraction with end_turn), the loop automatically continues.

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
