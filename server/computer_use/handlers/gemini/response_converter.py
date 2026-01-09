"""
Gemini response conversion utilities.

This module contains utilities for converting Gemini responses to Anthropic format.
"""

from typing import Any

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.handlers.utils.key_mapping_utils import normalize_key_combo
from server.computer_use.logging import logger


def process_computer_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Process computer tool input, normalizing action names and parameters.

    Args:
        tool_name: Name of the tool being called
        tool_input: Raw tool input

    Returns:
        Processed tool input
    """
    # Computer tool action names exposed as individual functions
    COMPUTER_ACTIONS = {
        'screenshot',
        'left_click',
        'mouse_move',
        'type',
        'key',
        'scroll',
        'left_click_drag',
        'right_click',
        'middle_click',
        'double_click',
        'left_mouse_down',
        'left_mouse_up',
        'hold_key',
        'wait',
    }

    # If called as an action function, embed action name
    if tool_name in COMPUTER_ACTIONS:
        tool_input = tool_input or {}
        tool_input['action'] = tool_name

    # Convert coordinate list to tuple if present
    if 'coordinate' in tool_input and isinstance(tool_input['coordinate'], list):
        tool_input['coordinate'] = tuple(tool_input['coordinate'])

    # Map legacy 'click' action to 'left_click' for compatibility
    if tool_input.get('action') == 'click':
        tool_input['action'] = 'left_click'

    action = tool_input.get('action')

    # Normalize key combos and key/text field for key-like actions
    if action in {'key', 'hold_key'}:
        if 'text' not in tool_input and 'key' in tool_input:
            # Remap key -> text
            tool_input['text'] = tool_input.pop('key')
        if 'text' in tool_input and isinstance(tool_input['text'], str):
            tool_input['text'] = normalize_key_combo(tool_input['text'])

    # Special handling for scroll: ensure scroll_amount is int and direction is valid
    if action == 'scroll':
        # scroll_amount should be int (wheel notches)
        if 'scroll_amount' in tool_input:
            try:
                tool_input['scroll_amount'] = int(tool_input['scroll_amount'])
            except Exception:
                logger.warning(
                    f'scroll_amount could not be converted to int: '
                    f'{tool_input.get("scroll_amount")}'
                )
        # scroll_direction should be one of the allowed values
        allowed_directions = {'up', 'down', 'left', 'right'}
        if 'scroll_direction' in tool_input:
            direction = str(tool_input['scroll_direction']).lower()
            if direction not in allowed_directions:
                logger.warning(f'Invalid scroll_direction: {direction}')
            tool_input['scroll_direction'] = direction

    # make sure api_type is 20250124
    tool_input['api_type'] = 'computer_20250124'
    return tool_input


def process_extraction_tool(tool_input: dict) -> dict:
    """
    Process extraction tool input, ensuring proper data structure.

    Args:
        tool_input: Raw tool input

    Returns:
        Processed tool input with proper data structure
    """
    logger.debug(f'Processing extraction tool - original input: {tool_input}')

    # Gemini sends {name: ..., result: ...} directly based on our schema
    # But our extraction tool expects {data: {name: ..., result: ...}}
    if 'data' not in tool_input:
        # If 'data' field is missing but we have name and result, wrap them
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
                f'Extraction tool call missing required fields. '
                f'Has: {tool_input.keys()}, needs: name, result'
            )
    else:
        # data field already exists, validate its structure
        extraction_data = tool_input['data']
        logger.debug(f"Extraction tool already has 'data' field: {extraction_data}")
        if not isinstance(extraction_data, dict):
            logger.warning(f'Extraction data is not a dict: {type(extraction_data)}')
        elif 'name' not in extraction_data or 'result' not in extraction_data:
            logger.warning(
                f'Extraction data missing required fields. '
                f'Has: {extraction_data.keys()}, needs: name, result'
            )

    return tool_input


def convert_function_call(
    function_call: dict[str, Any], call_id: str
) -> BetaContentBlockParam:
    """
    Convert a single Gemini function call to Anthropic format.

    Args:
        function_call: Gemini function call dict with 'name' and 'args'
        call_id: Unique ID for this tool call

    Returns:
        Anthropic tool use block
    """
    try:
        tool_name = function_call.get('name', '')
        tool_input = function_call.get('args', {})

        # Log the raw tool input for debugging
        logger.debug(f'Processing function call: {tool_name} (id: {call_id})')

        # Computer tool action names exposed as individual functions
        COMPUTER_ACTIONS = {
            'screenshot',
            'left_click',
            'mouse_move',
            'type',
            'key',
            'scroll',
            'left_click_drag',
            'right_click',
            'middle_click',
            'double_click',
            'left_mouse_down',
            'left_mouse_up',
            'hold_key',
            'wait',
        }

        # Special handling for computer tool or any of its action functions
        if tool_name == 'computer' or tool_name in COMPUTER_ACTIONS:
            tool_input = process_computer_tool(tool_name, tool_input)
            # Always emit a single Anthropic tool_use for 'computer'
            tool_name = 'computer'
            logger.debug(
                f'Added computer tool_use from action {function_call.get("name")} '
                f'- id: {call_id}'
            )

        # Special handling for extraction tool
        elif tool_name == 'extraction':
            tool_input = process_extraction_tool(tool_input)

        # Create the tool use block
        return BetaToolUseBlockParam(
            type='tool_use',
            id=call_id,
            name=tool_name,
            input=tool_input,
        )

    except Exception as e:
        logger.error(f'Failed to process function call: {function_call}, error: {e}')
        # Return error as text block
        return BetaTextBlockParam(
            type='text',
            text=f'Error processing function call {function_call.get("name", "unknown")}: {e}',
        )


def convert_gemini_to_anthropic_response(
    response: Any,
) -> tuple[list[BetaContentBlockParam], str]:
    """
    Convert Gemini response to Anthropic format blocks and stop reason.

    Maps Gemini's finish_reason to Anthropic's stop_reason:
    - 'STOP' -> 'end_turn'
    - 'MAX_TOKENS' -> 'max_tokens'
    - 'TOOL_CODE' / function calls present -> 'tool_use'
    - 'SAFETY' -> 'end_turn' (with safety note)
    """
    # Gemini finish reason to Anthropic stop reason mapping
    STOP_REASON_MAP = {
        'STOP': 'end_turn',
        'MAX_TOKENS': 'max_tokens',
        'SAFETY': 'end_turn',
        'RECITATION': 'end_turn',
        'OTHER': 'end_turn',
        'BLOCKLIST': 'end_turn',
        'PROHIBITED_CONTENT': 'end_turn',
        'SPII': 'end_turn',
    }

    content_blocks: list[BetaContentBlockParam] = []

    # Log the full response for debugging
    logger.debug(f'Full Gemini response object: {response}')

    # Extract candidates from Gemini response
    # Response structure: response.candidates[0].content.parts
    candidates = getattr(response, 'candidates', [])
    if not candidates:
        logger.warning('No candidates in Gemini response')
        return content_blocks, 'end_turn'

    candidate = candidates[0]
    content = getattr(candidate, 'content', None)
    finish_reason = getattr(candidate, 'finish_reason', 'STOP')

    # Convert finish_reason enum to string if needed
    if hasattr(finish_reason, 'name'):
        finish_reason = finish_reason.name
    finish_reason = str(finish_reason)

    logger.debug(
        f'Gemini candidate extracted - finish_reason: {finish_reason}, '
        f'has_content: {content is not None}'
    )

    if content is None:
        return content_blocks, STOP_REASON_MAP.get(finish_reason, 'end_turn')

    # Process parts
    parts = getattr(content, 'parts', [])
    function_call_count = 0

    for idx, part in enumerate(parts):
        # Check for text
        text = getattr(part, 'text', None)
        if text:
            content_blocks.append(BetaTextBlockParam(type='text', text=text))

        # Check for function call
        function_call = getattr(part, 'function_call', None)
        if function_call:
            # Generate unique ID for this tool call
            call_id = f'toolu_{idx:02d}'
            function_call_count += 1

            # Convert to dict format
            fc_dict = {
                'name': getattr(function_call, 'name', ''),
                'args': dict(getattr(function_call, 'args', {})),
            }

            logger.debug(f'Gemini function call: {fc_dict["name"]} (id: {call_id})')

            block = convert_function_call(fc_dict, call_id)
            content_blocks.append(block)

    # Determine stop reason
    if function_call_count > 0:
        stop_reason = 'tool_use'
    else:
        stop_reason = STOP_REASON_MAP.get(finish_reason, 'end_turn')

    logger.debug(
        f'Converted {len(content_blocks)} content blocks, stop_reason: {stop_reason}'
    )

    return content_blocks, stop_reason
