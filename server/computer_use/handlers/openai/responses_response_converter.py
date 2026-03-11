"""Convert OpenAI Responses API outputs into Anthropic-style tool blocks."""

from __future__ import annotations

import json
from typing import Any

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.handlers.utils.key_mapping_utils import normalize_key_combo
from server.computer_use.logging import logger

from .responses_message_converter import (
    make_openai_computer_tool_use_id,
    make_openai_function_tool_use_id,
)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return list(value)


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, 'model_dump'):
        return value.model_dump()
    if hasattr(value, '__dict__'):
        return {
            k: v
            for k, v in value.__dict__.items()
            if not k.startswith('_') and v is not None
        }
    return {}


def _extract_coordinate(action_data: dict[str, Any]) -> tuple[int, int] | None:
    coordinate = action_data.get('coordinate')
    if isinstance(coordinate, (list, tuple)) and len(coordinate) == 2:
        return int(coordinate[0]), int(coordinate[1])

    x = action_data.get('x')
    y = action_data.get('y')
    if x is None or y is None:
        return None
    return int(x), int(y)


def _convert_scroll_action(action_data: dict[str, Any]) -> dict[str, Any]:
    direction = action_data.get('scroll_direction')
    amount = action_data.get('scroll_amount')
    if direction is not None and amount is not None:
        return {
            'action': 'scroll',
            'scroll_direction': str(direction).lower(),
            'scroll_amount': abs(int(amount)),
        }

    horizontal = action_data.get('scroll_x', action_data.get('x', 0)) or 0
    vertical = action_data.get('scroll_y', action_data.get('y', 0)) or 0

    if abs(horizontal) > abs(vertical):
        direction = 'right' if horizontal > 0 else 'left'
        amount = abs(int(horizontal))
    else:
        direction = 'down' if vertical > 0 else 'up'
        amount = abs(int(vertical))

    return {
        'action': 'scroll',
        'scroll_direction': direction,
        'scroll_amount': amount,
    }


def _convert_keypress_action(action_data: dict[str, Any]) -> dict[str, Any]:
    keys = action_data.get('keys')
    if isinstance(keys, list):
        key_text = '+'.join(str(key) for key in keys if key)
    else:
        key_text = str(
            action_data.get('text')
            or action_data.get('key')
            or action_data.get('keys')
            or ''
        )

    return {
        'action': 'key',
        'text': normalize_key_combo(key_text),
    }


def _convert_action_to_tool_use(
    call_id: str,
    action_data: dict[str, Any],
    index: int,
) -> BetaContentBlockParam:
    action_type = str(action_data.get('type') or '').lower()
    tool_use_id = make_openai_computer_tool_use_id(call_id, index)

    if action_type == 'screenshot':
        return BetaToolUseBlockParam(
            type='tool_use',
            id=tool_use_id,
            name='computer',
            input={'action': 'screenshot'},
        )

    if action_type in {'click', 'double_click', 'move', 'drag'}:
        coordinate = _extract_coordinate(action_data)
        action_name_map = {
            'click': 'left_click',
            'double_click': 'double_click',
            'move': 'mouse_move',
            'drag': 'left_click_drag',
        }
        input_data: dict[str, Any] = {'action': action_name_map[action_type]}
        if coordinate is not None:
            input_data['coordinate'] = coordinate
        return BetaToolUseBlockParam(
            type='tool_use',
            id=tool_use_id,
            name='computer',
            input=input_data,
        )

    if action_type == 'keypress':
        return BetaToolUseBlockParam(
            type='tool_use',
            id=tool_use_id,
            name='computer',
            input=_convert_keypress_action(action_data),
        )

    if action_type == 'type':
        return BetaToolUseBlockParam(
            type='tool_use',
            id=tool_use_id,
            name='computer',
            input={'action': 'type', 'text': str(action_data.get('text') or '')},
        )

    if action_type == 'scroll':
        return BetaToolUseBlockParam(
            type='tool_use',
            id=tool_use_id,
            name='computer',
            input=_convert_scroll_action(action_data),
        )

    if action_type == 'wait':
        duration = action_data.get('duration')
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            duration = 1.0
        return BetaToolUseBlockParam(
            type='tool_use',
            id=tool_use_id,
            name='computer',
            input={'action': 'wait', 'duration': duration},
        )

    logger.warning(f'Unsupported OpenAI computer action type: {action_type}')
    return BetaToolUseBlockParam(
        type='tool_use',
        id=tool_use_id,
        name='ui_not_as_expected',
        input={'reasoning': f'Unsupported OpenAI computer action: {action_type}'},
    )


def _response_message_to_text_blocks(item: Any) -> list[BetaContentBlockParam]:
    blocks: list[BetaContentBlockParam] = []
    for content_item in _to_list(_get(item, 'content') or []):
        content_type = str(_get(content_item, 'type') or '').lower()
        if content_type in {'output_text', 'text'}:
            text = _get(content_item, 'text')
            if text:
                blocks.append(BetaTextBlockParam(type='text', text=str(text)))
    return blocks


def _response_function_call_to_tool_use(item: Any) -> BetaContentBlockParam:
    arguments_raw = _get(item, 'arguments') or '{}'
    try:
        arguments = json.loads(arguments_raw)
    except json.JSONDecodeError:
        logger.warning(f'Invalid OpenAI function call arguments: {arguments_raw}')
        arguments = {}

    call_id = str(_get(item, 'call_id') or _get(item, 'id') or '')
    return BetaToolUseBlockParam(
        type='tool_use',
        id=make_openai_function_tool_use_id(call_id),
        name=str(_get(item, 'name') or ''),
        input=arguments,
    )


def convert_openai_responses_to_anthropic_response(
    response: Any,
) -> tuple[list[BetaContentBlockParam], str, dict[str, Any]]:
    content_blocks: list[BetaContentBlockParam] = []
    provider_state: dict[str, Any] = {
        'last_response_id': str(_get(response, 'id') or ''),
        'model_family': 'openai_responses_computer',
    }

    for item in _to_list(_get(response, 'output') or []):
        item_type = str(_get(item, 'type') or '').lower()

        if item_type == 'message':
            content_blocks.extend(_response_message_to_text_blocks(item))
            continue

        if item_type == 'function_call':
            content_blocks.append(_response_function_call_to_tool_use(item))
            continue

        if item_type != 'computer_call':
            continue

        call_id = str(_get(item, 'call_id') or _get(item, 'id') or '')
        actions = [_to_dict(action) for action in _to_list(_get(item, 'actions') or [])]

        has_screenshot = False
        for index, action_data in enumerate(actions):
            if str(action_data.get('type') or '').lower() == 'screenshot':
                has_screenshot = True
            content_blocks.append(
                _convert_action_to_tool_use(call_id, action_data, index)
            )

        if not has_screenshot:
            content_blocks.append(
                BetaToolUseBlockParam(
                    type='tool_use',
                    id=make_openai_computer_tool_use_id(call_id, len(actions)),
                    name='computer',
                    input={'action': 'screenshot'},
                )
            )

        pending_safety_checks = _get(item, 'pending_safety_checks')
        if pending_safety_checks:
            provider_state['pending_safety_checks'] = pending_safety_checks

    status = str(_get(response, 'status') or '').lower()
    if status == 'incomplete':
        stop_reason = 'max_tokens'
    elif any(
        isinstance(block, dict) and block.get('type') == 'tool_use'
        for block in content_blocks
    ):
        stop_reason = 'tool_use'
    else:
        stop_reason = 'end_turn'

    if not provider_state.get('pending_safety_checks'):
        provider_state.pop('pending_safety_checks', None)

    return content_blocks, stop_reason, provider_state
