"""Stateless converters for messages, tools, and provider output.

Handlers should call these pure helpers to keep logic DRY and testable.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, List, Tuple, cast

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
    BetaToolUnionParam,
)

from openai.types.responses import (
    Response,
    ResponseInputParam,
    ComputerToolParam,
    FunctionToolParam,
)
from openai.types.responses.easy_input_message_param import EasyInputMessageParam
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
)

from server.computer_use.utils import normalize_key_combo, derive_center_coordinate


# ------------------------- Tool Converters -------------------------


def anthropic_tools_to_openai_functions(
    tools: List[BetaToolUnionParam],
) -> List[FunctionToolParam]:
    fns: List[FunctionToolParam] = []
    for t in tools:
        if t.get('name') == 'computer':
            continue
        fn: FunctionToolParam = cast(
            FunctionToolParam,
            {
                'type': 'function',
                'name': str(t['name']),
                'description': str(t.get('description') or f'Tool: {t["name"]}'),
                'strict': False,
                'parameters': cast(
                    dict[str, Any],
                    t.get('input_schema') or {'type': 'object', 'properties': {}},
                ),
            },
        )
        fns.append(fn)
    return fns


def extract_display_from_computer_tool(
    tools: List[BetaToolUnionParam], default: Tuple[int, int] = (1024, 768)
) -> Tuple[int, int]:
    width, height = default
    for t in tools:
        if t.get('name') == 'computer':
            width = int(t.get('width') or width)
            height = int(t.get('height') or height)
    return width, height


def build_openai_preview_tool(
    display: Tuple[int, int], environment: str = 'windows'
) -> ComputerToolParam:
    w, h = display
    return cast(
        ComputerToolParam,
        {
            'type': 'computer_use_preview',
            'display_width': w,
            'display_height': h,
            'environment': environment,
        },
    )


# ------------------------ Message Converters -----------------------


def beta_messages_to_openai_responses_input(
    messages: List[BetaMessageParam], image_detail: str = 'auto'
) -> ResponseInputParam:
    provider_messages: ResponseInputParam = []
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content')

        if isinstance(content, str):
            if role == 'user':
                provider_messages.append(
                    cast(
                        EasyInputMessageParam,
                        {
                            'role': 'user',
                            'content': [{'type': 'input_text', 'text': content}],
                        },
                    )
                )
            else:
                provider_messages.append(
                    cast(
                        EasyInputMessageParam,
                        {
                            'role': 'user',
                            'content': [
                                {
                                    'type': 'input_text',
                                    'text': f'Assistant said: {content}',
                                }
                            ],
                        },
                    )
                )
        elif isinstance(content, list):
            input_parts: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get('type')
                if btype == 'text':
                    text_val = block.get('text', '')
                    if text_val:
                        input_parts.append(
                            {'type': 'input_text', 'text': str(text_val)}
                        )
                elif btype == 'image':
                    source = block.get('source', {})
                    if source.get('type') == 'base64' and source.get('data'):
                        data_url = f'data:{source.get("media_type", "image/png")};base64,{source.get("data")}'
                        input_parts.append(
                            {
                                'type': 'input_image',
                                'detail': image_detail,
                                'image_url': data_url,
                            }
                        )
                elif btype == 'tool_result':
                    text_content = ''
                    image_data = None
                    if 'error' in block:
                        text_content = str(block['error'])
                    else:
                        for ci in block.get('content', []) or []:
                            if isinstance(ci, dict):
                                if ci.get('type') == 'text':
                                    text_content = ci.get('text', '')
                                elif (
                                    ci.get('type') == 'image'
                                    and ci.get('source', {}).get('type') == 'base64'
                                ):
                                    image_data = ci.get('source', {}).get('data')
                    if text_content:
                        input_parts.append(
                            {'type': 'input_text', 'text': str(text_content)}
                        )
                    if image_data:
                        input_parts.append(
                            {
                                'type': 'input_image',
                                'detail': image_detail,
                                'image_url': f'data:image/png;base64,{image_data}',
                            }
                        )
            if input_parts:
                provider_messages.append(
                    cast(
                        EasyInputMessageParam, {'role': 'user', 'content': input_parts}
                    )
                )
    return provider_messages


def beta_messages_to_openai_chat(
    messages: List[BetaMessageParam],
) -> List[ChatCompletionMessageParam]:
    provider_messages: list[ChatCompletionMessageParam] = []
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content')
        if isinstance(content, str):
            if role == 'user':
                provider_messages.append(
                    cast(
                        ChatCompletionMessageParam, {'role': 'user', 'content': content}
                    )
                )
            else:
                provider_messages.append(
                    cast(
                        ChatCompletionMessageParam,
                        {'role': 'user', 'content': f'Assistant said: {content}'},
                    )
                )
        elif isinstance(content, list):
            parts: list[ChatCompletionContentPartParam] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get('type')
                if btype == 'text':
                    txt = block.get('text', '')
                    if txt:
                        parts.append(
                            cast(
                                ChatCompletionContentPartTextParam,
                                {'type': 'text', 'text': str(txt)},
                            )
                        )
                elif btype == 'image':
                    source = block.get('source', {})
                    if source.get('type') == 'base64' and source.get('data'):
                        parts.append(
                            cast(
                                ChatCompletionContentPartImageParam,
                                {
                                    'type': 'image_url',
                                    'image_url': {
                                        'url': f'data:{source.get("media_type", "image/png")};base64,{source.get("data")}',
                                    },
                                },
                            )
                        )
                elif btype == 'tool_result':
                    text_content = ''
                    image_data = None
                    if 'error' in block:
                        text_content = str(block['error'])
                    else:
                        for ci in block.get('content', []) or []:
                            if isinstance(ci, dict):
                                if ci.get('type') == 'text':
                                    text_content = ci.get('text', '')
                                elif (
                                    ci.get('type') == 'image'
                                    and ci.get('source', {}).get('type') == 'base64'
                                ):
                                    image_data = ci.get('source', {}).get('data')
                    if text_content:
                        parts.append(
                            cast(
                                ChatCompletionContentPartTextParam,
                                {'type': 'text', 'text': str(text_content)},
                            )
                        )
                    if image_data:
                        parts.append(
                            cast(
                                ChatCompletionContentPartImageParam,
                                {
                                    'type': 'image_url',
                                    'image_url': {
                                        'url': f'data:image/png;base64,{image_data}'
                                    },
                                },
                            )
                        )
            if parts:
                provider_messages.append(
                    cast(ChatCompletionMessageParam, {'role': 'user', 'content': parts})
                )
    return provider_messages


# ------------------------- Output Converters -----------------------


def map_cua_action_to_computer_input(action: Any) -> dict:
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    atype = _get(action, 'type')
    mapped: dict[str, Any] = {}

    if atype == 'click':
        button = _get(action, 'button', 'left')
        x = _get(action, 'x')
        y = _get(action, 'y')
        mapped['action'] = (
            'left_click'
            if button == 'left'
            else 'right_click'
            if button == 'right'
            else 'middle_click'
        )
        if isinstance(x, int) and isinstance(y, int):
            mapped['coordinate'] = (x, y)
    elif atype == 'double_click':
        x = _get(action, 'x')
        y = _get(action, 'y')
        mapped['action'] = 'double_click'
        if isinstance(x, int) and isinstance(y, int):
            mapped['coordinate'] = (x, y)
    elif atype == 'scroll':
        sx = int(_get(action, 'scroll_x') or 0)
        sy = int(_get(action, 'scroll_y') or 0)
        if abs(sy) >= abs(sx):
            mapped['scroll_direction'] = 'down' if sy > 0 else 'up'
            mapped['scroll_amount'] = abs(sy)
        else:
            mapped['scroll_direction'] = 'right' if sx > 0 else 'left'
            mapped['scroll_amount'] = abs(sx)
        mapped['action'] = 'scroll'
    elif atype == 'type':
        mapped['action'] = 'type'
        text_val = _get(action, 'text')
        if text_val is not None:
            mapped['text'] = text_val
    elif atype in ('keypress', 'key', 'key_event'):
        keys = _get(action, 'keys')
        key = _get(action, 'key')
        combo = None
        if isinstance(keys, list) and keys:
            combo = '+'.join(str(k) for k in keys)
        elif isinstance(key, str):
            combo = key
        if combo:
            mapped['action'] = 'key'
            mapped['text'] = normalize_key_combo(combo)
        else:
            mapped['action'] = 'screenshot'
    elif atype == 'wait':
        mapped['action'] = 'wait'
        ms = _get(action, 'ms') or _get(action, 'duration_ms')
        try:
            mapped['duration'] = (float(ms) / 1000.0) if ms is not None else 1.0
        except Exception:
            mapped['duration'] = 1.0
    elif atype == 'screenshot':
        mapped['action'] = 'screenshot'
    elif atype == 'cursor_position':
        x = _get(action, 'x')
        y = _get(action, 'y')
        mapped['action'] = 'mouse_move'
        if isinstance(x, int) and isinstance(y, int):
            mapped['coordinate'] = (x, y)
    else:
        mapped['action'] = 'screenshot'
    return mapped


def responses_output_to_blocks(
    response: Response,
) -> tuple[List[BetaContentBlockParam], str]:
    content_blocks: list[BetaContentBlockParam] = []
    output_items = getattr(response, 'output', None) or []

    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    found_computer_call = False
    created_tool_call_counter = 0
    for item in output_items:
        itype = _get(item, 'type')
        if itype == 'reasoning':
            summary_items = _get(item, 'summary') or []
            for s in summary_items:
                txt = _get(s, 'text')
                if txt:
                    content_blocks.append(BetaTextBlockParam(type='text', text=txt))
        elif itype == 'computer_call':
            found_computer_call = True
            try:
                action = _get(item, 'action') or {}
                tool_input = map_cua_action_to_computer_input(action)
            except Exception:
                tool_input = {'action': 'screenshot'}
            tool_use_block = BetaToolUseBlockParam(
                type='tool_use',
                id=_get(item, 'id') or _get(item, 'call_id') or 'call_0',
                name='computer',
                input=tool_input,
            )
            content_blocks.append(tool_use_block)
        elif itype in ('tool_call', 'function_call'):
            created_tool_call_counter += 1
            tool_name = (
                _get(item, 'name')
                or _get(_get(item, 'function', {}), 'name')
                or 'unknown_tool'
            )
            call_id = (
                _get(item, 'id')
                or _get(item, 'call_id')
                or f'call_{created_tool_call_counter}'
            )
            raw_args = _get(item, 'arguments') or _get(
                _get(item, 'function', {}), 'arguments'
            )
            tool_input: dict[str, Any] = {}
            if isinstance(raw_args, str):
                try:
                    tool_input = json.loads(raw_args)
                except Exception:
                    tool_input = {}
            elif isinstance(raw_args, dict):
                tool_input = raw_args
            if tool_name == 'extraction' and 'data' not in tool_input:
                if 'name' in tool_input and 'result' in tool_input:
                    original_input = tool_input.copy()
                    tool_input = {
                        'data': {
                            'name': original_input['name'],
                            'result': original_input['result'],
                        }
                    }
            tool_use_block = BetaToolUseBlockParam(
                type='tool_use', id=call_id, name=tool_name, input=tool_input
            )
            content_blocks.append(tool_use_block)

    has_tool_use = any(cb.get('type') == 'tool_use' for cb in content_blocks)
    stop_reason = 'tool_use' if (has_tool_use or found_computer_call) else 'end_turn'
    return content_blocks, stop_reason


def chat_completion_text_to_blocks(
    text: str,
) -> tuple[List[BetaContentBlockParam], str]:
    content_blocks: list[BetaContentBlockParam] = []
    raw_text = text or ''

    # Thought
    m = re.search(r'Thought:\s*(.+?)(?=\n\s*Action:|\Z)', raw_text, re.S)
    if m:
        thought = m.group(1).strip()
        if thought:
            content_blocks.append(BetaTextBlockParam(type='text', text=thought))

    # Action
    action_str = ''
    am = re.search(r'Action:\s*(.+)\Z', raw_text, re.S)
    if am:
        action_str = am.group(1).strip()
    if not action_str:
        return content_blocks, 'end_turn'

    # potentially multiple calls separated by blank lines
    raw_actions = [
        seg.strip() for seg in re.split(r'\)\s*\n\s*\n', action_str) if seg.strip()
    ]
    created_tool_blocks = 0
    for seg in raw_actions:
        seg2 = seg if seg.endswith(')') else (seg + ')')
        try:
            node = ast.parse(seg2, mode='eval')
            if not isinstance(node, ast.Expression) or not isinstance(
                node.body, ast.Call
            ):
                continue
            call = cast(ast.Call, node.body)
            # function name
            if isinstance(call.func, ast.Name):
                fname = call.func.id
            elif isinstance(call.func, ast.Attribute):
                fname = call.func.attr
            else:
                fname = ''
            # kwargs
            kwargs: dict[str, Any] = {}
            for kw in call.keywords:
                key = kw.arg or ''
                if isinstance(kw.value, ast.Constant):
                    val = kw.value.value
                elif hasattr(ast, 'Str') and isinstance(
                    kw.value, ast.Str
                ):  # py<3.8 compatibility
                    val = kw.value.s  # type: ignore[attr-defined]
                else:
                    val = seg2[kw.value.col_offset : kw.value.end_col_offset]  # type: ignore[attr-defined]
                kwargs[key] = val
            # map to our computer tool input
            tool_input: dict[str, Any] = {}
            f = (fname or '').lower()
            if f in {'click', 'left_single'}:
                center = derive_center_coordinate(
                    kwargs.get('start_box') or kwargs.get('point')
                )
                tool_input['action'] = 'left_click'
                if center:
                    tool_input['coordinate'] = center
            elif f in {'left_double'}:
                center = derive_center_coordinate(
                    kwargs.get('start_box') or kwargs.get('point')
                )
                tool_input['action'] = 'double_click'
                if center:
                    tool_input['coordinate'] = center
            elif f in {'right_single'}:
                center = derive_center_coordinate(
                    kwargs.get('start_box') or kwargs.get('point')
                )
                tool_input['action'] = 'right_click'
                if center:
                    tool_input['coordinate'] = center
            elif f in {'hover'}:
                center = derive_center_coordinate(
                    kwargs.get('start_box') or kwargs.get('point')
                )
                tool_input['action'] = 'mouse_move'
                if center:
                    tool_input['coordinate'] = center
            elif f in {'drag', 'select'}:
                s = derive_center_coordinate(
                    kwargs.get('start_box') or kwargs.get('start_point')
                )
                e = derive_center_coordinate(
                    kwargs.get('end_box') or kwargs.get('end_point')
                )
                tool_input['action'] = 'left_click_drag'
                if s:
                    tool_input['coordinate'] = s
                if e:
                    tool_input['to'] = list(e)
            elif f in {'hotkey', 'keypress', 'key', 'keydown'}:
                combo = kwargs.get('key') or kwargs.get('hotkey') or ''
                tool_input['action'] = 'key'
                if isinstance(combo, str) and combo:
                    tool_input['text'] = normalize_key_combo(combo)
            elif f in {'release', 'keyup'}:
                combo = kwargs.get('key') or ''
                tool_input['action'] = 'key'
                if isinstance(combo, str) and combo:
                    tool_input['text'] = normalize_key_combo(combo)
            elif f in {'type'}:
                txt = kwargs.get('content') or ''
                tool_input['action'] = 'type'
                if isinstance(txt, str):
                    tool_input['text'] = txt
            elif f in {'scroll'}:
                direction = (kwargs.get('direction') or '').lower()
                center = derive_center_coordinate(
                    kwargs.get('start_box') or kwargs.get('point')
                )
                tool_input['action'] = 'scroll'
                if direction in {'up', 'down', 'left', 'right'}:
                    tool_input['scroll_direction'] = direction
                tool_input['scroll_amount'] = 5
                if center:
                    tool_input['coordinate'] = center
            elif f in {'wait'}:
                tool_input['action'] = 'wait'
                tool_input['duration'] = 1.0
            elif f in {'finished'}:
                fin = kwargs.get('content')
                if isinstance(fin, str) and fin:
                    content_blocks.append(BetaTextBlockParam(type='text', text=fin))
                continue
            else:
                tool_input['action'] = 'screenshot'

            tool_use_block = BetaToolUseBlockParam(
                type='tool_use',
                id=f'uitars_call_{created_tool_blocks}',
                name='computer',
                input=tool_input,
            )
            created_tool_blocks += 1
            content_blocks.append(tool_use_block)
        except Exception:
            continue

    stop_reason = (
        'tool_use'
        if any(cb.get('type') == 'tool_use' for cb in content_blocks)
        else 'end_turn'
    )
    return content_blocks, stop_reason
