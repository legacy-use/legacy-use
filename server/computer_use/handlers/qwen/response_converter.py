"""
Qwen Bedrock response conversion utilities.

Converts Bedrock Converse responses into Anthropic-style content blocks.
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.handlers.utils.key_mapping_utils import normalize_key_combo
from server.computer_use.logging import logger

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
    'triple_click',
    'left_mouse_down',
    'left_mouse_up',
    'hold_key',
    'wait',
}


def _get_attr(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def process_computer_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
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
                    'scroll_amount could not be converted to int: '
                    f'{tool_input.get("scroll_amount")}'
                )
        allowed_directions = {'up', 'down', 'left', 'right'}
        if 'scroll_direction' in tool_input:
            direction = str(tool_input['scroll_direction']).lower()
            if direction not in allowed_directions:
                logger.warning(f'Invalid scroll_direction: {direction}')
            tool_input['scroll_direction'] = direction

    tool_input['api_type'] = 'computer_20250124'
    return tool_input


def process_extraction_tool(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    if 'data' not in tool_input:
        if 'name' in tool_input and 'result' in tool_input:
            tool_input = {
                'data': {
                    'name': tool_input['name'],
                    'result': tool_input['result'],
                }
            }
        else:
            logger.warning(
                'Extraction tool call missing required fields. '
                f'Has: {tool_input.keys()}, needs: name, result'
            )
    return tool_input


def _convert_tool_use(tool_use: Dict[str, Any]) -> BetaToolUseBlockParam:
    tool_use_id = str(tool_use.get('toolUseId') or tool_use.get('toolUseID') or '')
    if not tool_use_id:
        tool_use_id = f'toolu_bedrock_{uuid4().hex}'

    tool_name = str(tool_use.get('name') or '')
    tool_input = tool_use.get('input') or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool_name == 'computer' or tool_name in COMPUTER_ACTIONS:
        tool_input = process_computer_tool(tool_name, tool_input)
        tool_name = 'computer'
    elif tool_name == 'extraction':
        tool_input = process_extraction_tool(tool_input)

    return {
        'type': 'tool_use',
        'id': tool_use_id,
        'name': tool_name,
        'input': tool_input,
    }


def convert_bedrock_to_anthropic_response(
    response: Any,
) -> tuple[List[BetaContentBlockParam], str]:
    content_blocks: List[BetaContentBlockParam] = []

    output = _get_attr(response, 'output') or {}
    message = _get_attr(output, 'message') or {}
    contents = _get_attr(message, 'content') or []

    for item in contents:
        if not isinstance(item, dict):
            continue
        if 'text' in item:
            content_blocks.append(
                BetaTextBlockParam(type='text', text=str(item.get('text') or ''))
            )
            continue
        tool_use = item.get('toolUse')
        if tool_use:
            content_blocks.append(_convert_tool_use(tool_use))

    stop_reason_raw = (
        _get_attr(response, 'stopReason') or _get_attr(response, 'stop_reason') or ''
    )
    stop_reason_map = {
        'end_turn': 'end_turn',
        'tool_use': 'tool_use',
        'max_tokens': 'max_tokens',
        'stop_sequence': 'end_turn',
        'content_filtered': 'end_turn',
        'guardrail_intervened': 'end_turn',
    }
    stop_reason = stop_reason_map.get(str(stop_reason_raw), 'end_turn')

    return content_blocks, stop_reason
