"""Response conversion utilities for OpenAI handler."""

import json
from typing import Optional

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)
from openai.types.chat import ChatCompletion

from server.computer_use.handlers.utils.key_mapping_utils import (
    normalize_key_combo,
)
from server.computer_use.logging import logger


def process_computer_tool(
    tool_name: str, tool_input: dict, computer_actions: set[str]
) -> dict:
    """Process computer tool input, normalizing action names and parameters."""
    if tool_name in computer_actions:
        tool_input = tool_input or {}
        tool_input['action'] = tool_name

    if 'coordinate' in tool_input and isinstance(tool_input['coordinate'], list):
        tool_input['coordinate'] = tuple(tool_input['coordinate'])

    if tool_input.get('action') == 'click':
        tool_input['action'] = 'left_click'

    action = tool_input.get('action')

    if action in {'key', 'hold_key'}:
        if 'text' not in tool_input and 'key' in tool_input:
            tool_input['text'] = tool_input.pop('key')
        if 'text' in tool_input and isinstance(tool_input['text'], str):
            tool_input['text'] = normalize_key_combo(tool_input['text'])

    if action == 'scroll':
        if 'scroll_amount' in tool_input:
            try:
                tool_input['scroll_amount'] = int(tool_input['scroll_amount'])
            except Exception:
                logger.warning(
                    f'scroll_amount could not be converted to int: {tool_input.get("scroll_amount")}'
                )
        allowed_directions = {'up', 'down', 'left', 'right'}
        if 'scroll_direction' in tool_input:
            direction = str(tool_input['scroll_direction']).lower()
            if direction not in allowed_directions:
                logger.warning(f'Invalid scroll_direction: {direction}')
            tool_input['scroll_direction'] = direction

    tool_input['api_type'] = 'computer_20250124'
    return tool_input


def process_extraction_tool(tool_input: dict) -> dict:
    """Process extraction tool input, ensuring proper data structure."""
    logger.debug(f'Processing extraction tool - original input: {tool_input}')

    if 'data' not in tool_input:
        if 'name' in tool_input and 'result' in tool_input:
            original_input = tool_input.copy()
            tool_input = {
                'data': {
                    'name': tool_input['name'],
                    'result': tool_input['result'],
                }
            }
            logger.debug(
                f'Wrapped extraction data - from: {original_input} to: {tool_input}'
            )
        else:
            logger.warning(
                f'Extraction tool call missing required fields. Has: {tool_input.keys()}, needs: name, result'
            )
    else:
        extraction_data = tool_input['data']
        logger.debug(f"Extraction tool already has 'data' field: {extraction_data}")
        if not isinstance(extraction_data, dict):
            logger.warning(f'Extraction data is not a dict: {type(extraction_data)}')
        elif 'name' not in extraction_data or 'result' not in extraction_data:
            logger.warning(
                f'Extraction data missing required fields. Has: {extraction_data.keys()}, needs: name, result'
            )

    return tool_input


def convert_tool_call(tool_call, computer_actions: set[str]) -> BetaContentBlockParam:
    """Convert a single OpenAI tool call to Anthropic format."""
    try:
        tool_input = json.loads(tool_call.function.arguments)
        tool_name = tool_call.function.name

        logger.debug(f'Processing tool call: {tool_name} (id: {tool_call.id})')

        if tool_name == 'computer' or tool_name in computer_actions:
            tool_input = process_computer_tool(tool_name, tool_input, computer_actions)
            tool_name = 'computer'
            logger.debug(
                f'Added computer tool_use from action {tool_call.function.name} - id: {tool_call.id}'
            )
        elif tool_name == 'extraction':
            tool_input = process_extraction_tool(tool_input)

        return BetaToolUseBlockParam(
            type='tool_use',
            id=tool_call.id,
            name=tool_name,
            input=tool_input,
        )

    except json.JSONDecodeError as e:
        logger.error(
            f'Failed to parse tool arguments: {tool_call.function.arguments}, error: {e}'
        )
        return BetaTextBlockParam(
            type='text',
            text=f'Error parsing tool arguments for {tool_call.function.name}: {e}',
        )


def convert_from_openai_response(
    response: ChatCompletion,
    stop_reason_map: dict[str, str],
    computer_actions: set[str],
) -> tuple[list[BetaContentBlockParam], str]:
    """Convert OpenAI response to Anthropic format blocks and stop reason."""
    content_blocks: list[BetaContentBlockParam] = []

    logger.debug(f'Full OpenAI response object: {response}')

    message = response.choices[0].message
    logger.debug(
        f'OpenAI message extracted - content: {message.content is not None}, tool_calls: {len(message.tool_calls) if message.tool_calls else 0}'
    )

    if message.tool_calls:
        for tc in message.tool_calls:
            logger.debug(f'OpenAI tool call: {tc.function.name} (id: {tc.id})')

    if message.content:
        content_blocks.append(BetaTextBlockParam(type='text', text=message.content))

    if message.tool_calls:
        logger.debug(
            f'Converting {len(message.tool_calls)} tool calls from OpenAI response'
        )
        for tool_call in message.tool_calls:
            block = convert_tool_call(tool_call, computer_actions)
            content_blocks.append(block)
            logger.debug(
                f'Added to content blocks - tool: {tool_call.function.name}, id: {tool_call.id}'
            )

    finish_reason: Optional[str] = response.choices[0].finish_reason
    stop_reason = stop_reason_map.get(finish_reason, 'end_turn')

    return content_blocks, stop_reason
