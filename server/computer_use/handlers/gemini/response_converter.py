"""
Gemini response conversion utilities.

Converts Gemini responses into Anthropic-style content blocks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from uuid import uuid4

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.handlers.utils.key_mapping_utils import normalize_key_combo
from server.computer_use.logging import logger

from .mapping import (
    DEFAULT_SCROLL_AMOUNT,
    GEMINI_CALL_METADATA_KEY,
    denormalize_coordinate,
    get_display_dimensions,
)


def _get_attr(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _extract_thought_signature(part: Any) -> str | None:
    for key in ('thought_signature', 'thoughtSignature'):
        value = _get_attr(part, key)
        if value:
            return str(value)

    function_call = _get_attr(part, 'function_call') or _get_attr(part, 'functionCall')
    for key in ('thought_signature', 'thoughtSignature'):
        value = _get_attr(function_call, key)
        if value:
            return str(value)
    return None


def _extract_function_call(part: Any) -> Tuple[str | None, Dict[str, Any]]:
    function_call = _get_attr(part, 'function_call') or _get_attr(part, 'functionCall')
    if not function_call:
        return None, {}

    name = _get_attr(function_call, 'name')
    args = _get_attr(function_call, 'args') or {}
    if not isinstance(args, dict):
        args = {}
    return str(name) if name else None, args


def _build_tool_use_block(
    name: str,
    tool_input: Dict[str, Any],
    *,
    gemini_call: Dict[str, Any],
) -> BetaToolUseBlockParam:
    return {
        'type': 'tool_use',
        'id': f'toolu_gemini_{uuid4().hex}',
        'name': name,
        'input': tool_input,
        GEMINI_CALL_METADATA_KEY: gemini_call,
    }


def _convert_computer_function(
    function_name: str,
    args: Dict[str, Any],
    width: int,
    height: int,
) -> Tuple[str | None, Dict[str, Any]]:
    if function_name == 'click_at':
        coordinate = denormalize_coordinate(
            args.get('x', 0), args.get('y', 0), width, height
        )
        return 'computer', {'action': 'left_click', 'coordinate': coordinate}
    if function_name == 'hover_at':
        coordinate = denormalize_coordinate(
            args.get('x', 0), args.get('y', 0), width, height
        )
        return 'computer', {'action': 'mouse_move', 'coordinate': coordinate}
    if function_name == 'type_text_at':
        text = str(args.get('text') or '')
        if args.get('press_enter'):
            text = f'{text}\n'
        return 'computer', {'action': 'type', 'text': text}
    if function_name == 'key_combination':
        keys = str(args.get('keys') or '')
        return 'computer', {
            'action': 'key',
            'text': normalize_key_combo(keys),
        }
    if function_name == 'scroll_document':
        direction = args.get('direction')
        if direction is not None:
            direction = str(direction).lower()
        return 'computer', {
            'action': 'scroll',
            'scroll_direction': direction,
            'scroll_amount': DEFAULT_SCROLL_AMOUNT,
        }
    if function_name == 'scroll_at':
        direction = args.get('direction')
        if direction is not None:
            direction = str(direction).lower()
        magnitude = args.get('magnitude', DEFAULT_SCROLL_AMOUNT)
        try:
            magnitude = int(magnitude)
        except (TypeError, ValueError):
            magnitude = DEFAULT_SCROLL_AMOUNT
        coordinate = denormalize_coordinate(
            args.get('x', 0), args.get('y', 0), width, height
        )
        return 'computer', {
            'action': 'scroll',
            'scroll_direction': direction,
            'scroll_amount': magnitude,
            'coordinate': coordinate,
        }
    if function_name == 'drag_and_drop':
        coordinate = denormalize_coordinate(
            args.get('destination_x', args.get('x', 0)),
            args.get('destination_y', args.get('y', 0)),
            width,
            height,
        )
        return 'computer', {'action': 'left_click_drag', 'coordinate': coordinate}
    if function_name == 'wait_5_seconds':
        return 'computer', {'action': 'wait', 'duration': 5}

    # Custom computer actions
    if function_name in {
        'screenshot',
        'right_click',
        'middle_click',
        'double_click',
        'triple_click',
        'left_mouse_down',
        'left_mouse_up',
        'hold_key',
        'wait',
    }:
        tool_input: Dict[str, Any] = {'action': function_name}
        if 'coordinate' in args and isinstance(args['coordinate'], list):
            tool_input['coordinate'] = tuple(args['coordinate'])
        if 'text' in args:
            text_value = args.get('text')
            if function_name == 'hold_key' and isinstance(text_value, str):
                text_value = normalize_key_combo(text_value)
            tool_input['text'] = text_value
        if 'duration' in args:
            tool_input['duration'] = args.get('duration')
        return 'computer', tool_input

    return None, {}


def convert_gemini_to_anthropic_response(
    response: Any,
    *,
    computer_tool: Any | None = None,
) -> tuple[List[BetaContentBlockParam], str]:
    """
    Convert Gemini response to Anthropic format blocks and stop reason.
    """
    width, height = get_display_dimensions(computer_tool)
    content_blocks: List[BetaContentBlockParam] = []

    candidates = _get_attr(response, 'candidates') or []
    if not candidates:
        content_blocks.append(
            _build_tool_use_block(
                'computer',
                {'action': 'screenshot'},
                gemini_call={'name': 'screenshot', 'args': {}},
            )
        )
        return content_blocks, 'tool_use'

    candidate = candidates[0]
    content = _get_attr(candidate, 'content')
    parts = _get_attr(content, 'parts') or []

    for part in parts:
        text = _get_attr(part, 'text')
        if text:
            content_blocks.append(BetaTextBlockParam(type='text', text=str(text)))

        function_name, args = _extract_function_call(part)
        if not function_name:
            continue

        thought_signature = _extract_thought_signature(part)
        gemini_call = {
            'name': function_name,
            'args': args,
            'thought_signature': thought_signature,
        }

        if function_name in {'extraction', 'ui_not_as_expected', 'custom_action'}:
            tool_input = args or {}
            if function_name == 'extraction' and isinstance(tool_input, dict):
                if 'data' not in tool_input and all(
                    key in tool_input for key in ('name', 'result')
                ):
                    tool_input = {
                        'data': {
                            'name': tool_input.get('name'),
                            'result': tool_input.get('result'),
                        }
                    }
            content_blocks.append(
                _build_tool_use_block(
                    function_name, tool_input, gemini_call=gemini_call
                )
            )
            continue

        tool_name, tool_input = _convert_computer_function(
            function_name, args, width, height
        )
        if tool_name:
            content_blocks.append(
                _build_tool_use_block(tool_name, tool_input, gemini_call=gemini_call)
            )
        else:
            logger.warning(f'Unsupported Gemini function call: {function_name}')
            content_blocks.append(
                _build_tool_use_block(
                    'ui_not_as_expected',
                    {
                        'reasoning': f'Gemini function {function_name} is not supported.',
                    },
                    gemini_call=gemini_call,
                )
            )

    has_tool_use = any(block.get('type') == 'tool_use' for block in content_blocks)
    if not has_tool_use:
        content_blocks.append(
            _build_tool_use_block(
                'computer',
                {'action': 'screenshot'},
                gemini_call={'name': 'screenshot', 'args': {}},
            )
        )
        has_tool_use = True

    stop_reason = 'tool_use' if has_tool_use else 'end_turn'
    if any(
        block.get('type') == 'tool_use' and block.get('name') == 'extraction'
        for block in content_blocks
    ):
        stop_reason = 'end_turn'

    finish_reason = _get_attr(candidate, 'finish_reason')
    if finish_reason:
        finish_reason = str(finish_reason).lower()
        if 'max' in finish_reason or 'length' in finish_reason:
            stop_reason = 'max_tokens'

    return content_blocks, stop_reason
