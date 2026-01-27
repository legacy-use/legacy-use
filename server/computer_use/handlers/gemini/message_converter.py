"""
Gemini message conversion utilities.

Converts Anthropic-style messages into Gemini Content objects.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Tuple

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
)

from server.computer_use.handlers.utils.key_mapping_utils import normalize_key_combo
from server.computer_use.logging import logger

from .mapping import (
    DEFAULT_SCROLL_AMOUNT,
    GEMINI_CALL_METADATA_KEY,
    get_display_dimensions,
    normalize_coordinate,
)

DEFAULT_FUNCTION_RESPONSE_URL = 'about:blank'


def _extract_text_from_tool_result(block: BetaContentBlockParam) -> Tuple[str, bool]:
    if block.get('error'):
        return str(block.get('error') or ''), True

    is_error = bool(block.get('is_error'))
    text_chunks = []
    for content_item in block.get('content', []) or []:
        if isinstance(content_item, dict) and content_item.get('type') == 'text':
            text_chunks.append(str(content_item.get('text') or ''))
    return '\n'.join(t for t in text_chunks if t), is_error


def _extract_images_from_tool_result(
    block: BetaContentBlockParam,
) -> List[Dict[str, Any]]:
    image_parts: List[Dict[str, Any]] = []
    for content_item in block.get('content', []) or []:
        if isinstance(content_item, dict) and content_item.get('type') == 'image':
            source = content_item.get('source') or {}
            if source.get('type') != 'base64':
                continue
            data = source.get('data')
            if not data:
                continue
            try:
                image_bytes = base64.b64decode(data)
            except Exception:
                continue
            image_parts.append(
                {
                    'inline_data': {
                        'mime_type': source.get('media_type', 'image/png'),
                        'data': image_bytes,
                    }
                }
            )
    return image_parts


def _block_has_tool_results(content: List[Any]) -> bool:
    return any(
        isinstance(block, dict) and block.get('type') == 'tool_result'
        for block in content
    )


def _build_tool_call_part(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    part: Dict[str, Any] = {
        'function_call': {
            'name': tool_call.get('name') or '',
            'args': tool_call.get('args') or {},
        }
    }
    signature = tool_call.get('thought_signature') or tool_call.get('thoughtSignature')
    if signature:
        part['thought_signature'] = signature
    return part


def _computer_tool_use_to_gemini_call(
    tool_input: Dict[str, Any],
    width: int,
    height: int,
) -> Dict[str, Any] | None:
    action = tool_input.get('action')
    if not action:
        return None

    coordinate = tool_input.get('coordinate')
    coord_norm = None
    if isinstance(coordinate, (tuple, list)) and len(coordinate) == 2:
        coord_norm = normalize_coordinate(tuple(coordinate), width, height)

    if action == 'left_click' and coord_norm:
        return {'name': 'click_at', 'args': coord_norm}
    if action == 'mouse_move' and coord_norm:
        return {'name': 'hover_at', 'args': coord_norm}
    if action == 'type':
        args: Dict[str, Any] = {'text': tool_input.get('text') or ''}
        if coord_norm:
            args.update(coord_norm)
        return {'name': 'type_text_at', 'args': args}
    if action == 'key':
        keys = tool_input.get('text') or tool_input.get('key') or ''
        return {'name': 'key_combination', 'args': {'keys': normalize_key_combo(keys)}}
    if action == 'scroll':
        direction = tool_input.get('scroll_direction')
        magnitude = tool_input.get('scroll_amount', DEFAULT_SCROLL_AMOUNT)
        if coord_norm:
            return {
                'name': 'scroll_at',
                'args': {
                    **coord_norm,
                    'direction': direction,
                    'magnitude': magnitude,
                },
            }
        return {'name': 'scroll_document', 'args': {'direction': direction}}
    if action == 'left_click_drag' and coord_norm:
        return {
            'name': 'drag_and_drop',
            'args': {
                'x': coord_norm['x'],
                'y': coord_norm['y'],
                'destination_x': coord_norm['x'],
                'destination_y': coord_norm['y'],
            },
        }
    if action == 'wait':
        duration = tool_input.get('duration')
        if duration == 5:
            return {'name': 'wait_5_seconds', 'args': {}}
        return {'name': 'wait', 'args': {'duration': duration}}

    # Custom computer actions map to function name with the same action name.
    custom_args = {}
    if coordinate is not None:
        custom_args['coordinate'] = list(coordinate)
    if tool_input.get('text') is not None:
        custom_args['text'] = tool_input.get('text')
    if tool_input.get('duration') is not None:
        custom_args['duration'] = tool_input.get('duration')
    return {'name': action, 'args': custom_args}


def _tool_use_to_gemini_call(
    block: BetaContentBlockParam,
    width: int,
    height: int,
) -> Dict[str, Any] | None:
    if not isinstance(block, dict):
        return None

    meta = block.get(GEMINI_CALL_METADATA_KEY)
    if isinstance(meta, dict) and meta.get('name'):
        return meta

    name = block.get('name')
    tool_input = block.get('input') or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if name in {'extraction', 'ui_not_as_expected', 'custom_action'}:
        return {'name': name, 'args': tool_input}

    if name == 'computer':
        return _computer_tool_use_to_gemini_call(tool_input, width, height)

    if name:
        return {'name': name, 'args': tool_input}
    return None


def _tool_result_to_function_response(
    block: BetaContentBlockParam,
    tool_call_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, Any] | None:
    tool_use_id = str(block.get('tool_use_id') or '')
    if not tool_use_id:
        return None

    tool_call = tool_call_lookup.get(tool_use_id, {})
    name = tool_call.get('name') or tool_use_id

    text, is_error = _extract_text_from_tool_result(block)
    image_parts = _extract_images_from_tool_result(block)

    response_data: Dict[str, Any] = {'url': DEFAULT_FUNCTION_RESPONSE_URL}
    if is_error:
        response_data['error'] = text or 'Tool execution failed.'
    elif text:
        response_data['output'] = text
    else:
        response_data['output'] = 'Tool executed successfully.'

    function_response: Dict[str, Any] = {
        'name': name,
        'response': response_data,
    }
    if image_parts:
        function_response['parts'] = image_parts

    return {'function_response': function_response}


def convert_anthropic_to_gemini_messages(
    messages: List[BetaMessageParam],
    *,
    computer_tool: Any | None = None,
) -> List[Dict[str, Any]]:
    """
    Convert Anthropic-format messages to Gemini format.
    """
    width, height = get_display_dimensions(computer_tool)
    contents: List[Dict[str, Any]] = []
    tool_call_lookup: Dict[str, Dict[str, Any]] = {}

    msg_idx = 0
    while msg_idx < len(messages):
        msg = messages[msg_idx]
        role = msg.get('role')
        gemini_role = 'model' if role == 'assistant' else 'user'
        content = msg.get('content')

        if isinstance(content, str):
            contents.append({'role': gemini_role, 'parts': [{'text': content}]})
            msg_idx += 1
            continue

        if not isinstance(content, list):
            msg_idx += 1
            continue

        if role == 'user' and _block_has_tool_results(content):
            parts: List[Dict[str, Any]] = []
            while msg_idx < len(messages):
                current_msg = messages[msg_idx]
                current_content = current_msg.get('content')
                if (
                    current_msg.get('role') != 'user'
                    or not isinstance(current_content, list)
                    or not _block_has_tool_results(current_content)
                ):
                    break
                for block in current_content:
                    if isinstance(block, dict) and block.get('type') == 'tool_result':
                        fr_part = _tool_result_to_function_response(
                            block, tool_call_lookup
                        )
                        if fr_part:
                            parts.append(fr_part)
                msg_idx += 1

            if parts:
                contents.append({'role': 'user', 'parts': parts})
            continue

        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get('type')
            if block_type == 'text':
                parts.append({'text': block.get('text') or ''})
            elif block_type == 'image':
                source = block.get('source') or {}
                if source.get('type') != 'base64':
                    continue
                data = source.get('data')
                if not data:
                    continue
                try:
                    image_bytes = base64.b64decode(data)
                except Exception:
                    continue
                parts.append(
                    {
                        'inline_data': {
                            'mime_type': source.get('media_type', 'image/png'),
                            'data': image_bytes,
                        }
                    }
                )
            elif block_type == 'tool_use' and role == 'assistant':
                tool_call = _tool_use_to_gemini_call(block, width, height)
                if not tool_call:
                    continue
                tool_use_id = str(block.get('id') or '')
                if tool_use_id:
                    tool_call_lookup[tool_use_id] = tool_call
                parts.append(_build_tool_call_part(tool_call))

        if parts:
            contents.append({'role': gemini_role, 'parts': parts})

        msg_idx += 1

    logger.debug(
        f'Converted {len(messages)} messages to {len(contents)} Gemini contents'
    )
    return contents
