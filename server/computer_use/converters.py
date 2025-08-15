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
    ChatCompletionToolParam,
)
from server.computer_use.logging import logger

from server.computer_use.tools.base import BaseAnthropicTool
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


# -------------------- Internal spec → OpenAI functions --------------------


def _spec_to_openai_responses_function(spec: dict) -> FunctionToolParam:
    name = str(spec.get('name') or '')
    description = str(spec.get('description') or f'Tool: {name}')
    parameters = cast(
        dict[str, Any], spec.get('input_schema') or {'type': 'object', 'properties': {}}
    )
    return cast(
        FunctionToolParam,
        {
            'type': 'function',
            'name': name,
            'description': description,
            'strict': False,
            'parameters': parameters,
        },
    )


def internal_specs_to_openai_responses_functions(
    tools: List[BaseAnthropicTool],
) -> List[FunctionToolParam]:
    result: List[FunctionToolParam] = []
    for tool in tools:
        if getattr(tool, 'name', None) == 'computer':
            # Do not expand for CUA; preview tool replaces it
            continue
        result.append(_spec_to_openai_responses_function(tool.internal_spec()))
    return result


def _spec_to_openai_chat_function(spec: dict) -> ChatCompletionToolParam:
    name = str(spec.get('name') or '')
    description = str(spec.get('description') or f'Tool: {name}')
    parameters = cast(
        dict[str, Any], spec.get('input_schema') or {'type': 'object', 'properties': {}}
    )
    return cast(
        ChatCompletionToolParam,
        {
            'type': 'function',
            'function': {
                'name': name,
                'description': description,
                'parameters': parameters,
            },
        },
    )


def expand_computer_to_openai_chat_functions(
    tool: BaseAnthropicTool,
) -> List[ChatCompletionToolParam]:
    spec = tool.internal_spec()
    actions: list[dict] = cast(list[dict], spec.get('actions') or [])
    funcs: List[ChatCompletionToolParam] = []
    for action in actions:
        aname = str(action.get('name') or '')
        params = cast(dict[str, Any], action.get('params') or {})
        funcs.append(
            cast(
                ChatCompletionToolParam,
                {
                    'type': 'function',
                    'function': {
                        'name': aname,
                        'description': f'Computer action: {aname}',
                        'parameters': {
                            'type': 'object',
                            'properties': params,
                            'required': [],
                        },
                    },
                },
            )
        )
    return funcs


def internal_specs_to_openai_chat_functions(
    tools: List[BaseAnthropicTool],
) -> List[ChatCompletionToolParam]:
    result: List[ChatCompletionToolParam] = []
    for tool in tools:
        if getattr(tool, 'name', None) == 'computer':
            result.extend(expand_computer_to_openai_chat_functions(tool))
        else:
            result.append(_spec_to_openai_chat_function(tool.internal_spec()))
    return result


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
            elif role == 'assistant':
                provider_messages.append(
                    cast(
                        ChatCompletionMessageParam,
                        {'role': 'assistant', 'content': content},
                    )
                )
            else:
                # Fallback: treat unknown roles as user
                provider_messages.append(
                    cast(
                        ChatCompletionMessageParam,
                        {'role': 'user', 'content': str(content)},
                    )
                )
        elif isinstance(content, list):
            # For list content, preserve role: user → parts, assistant → collapse to text
            if role == 'user':
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
                        cast(
                            ChatCompletionMessageParam,
                            {'role': 'user', 'content': parts},
                        )
                    )
            elif role == 'assistant':
                # Collapse assistant blocks to a single text string; drop images/tool_result visuals
                texts: list[str] = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get('type') == 'text' and block.get('text'):
                        texts.append(str(block.get('text')))
                    elif block.get('type') == 'tool_result':
                        # include any textual parts from tool_result
                        for ci in block.get('content', []) or []:
                            if (
                                isinstance(ci, dict)
                                and ci.get('type') == 'text'
                                and ci.get('text')
                            ):
                                texts.append(str(ci.get('text')))
                content_str = '\n'.join(t for t in texts if t)
                provider_messages.append(
                    cast(
                        ChatCompletionMessageParam,
                        {'role': 'assistant', 'content': content_str},
                    )
                )
            else:
                # Fallback: treat as user with text-only collapse
                texts: list[str] = []
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get('type') == 'text'
                        and block.get('text')
                    ):
                        texts.append(str(block.get('text')))
                if texts:
                    provider_messages.append(
                        cast(
                            ChatCompletionMessageParam,
                            {'role': 'user', 'content': '\n'.join(texts)},
                        )
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
        # if no action, return the last block as the action
        return content_blocks, 'end_turn'

    # potentially multiple calls separated by blank lines
    raw_actions = [
        seg.strip() for seg in re.split(r'\)\s*\n\s*\n', action_str) if seg.strip()
    ]
    logger.info(f'Raw actions: {raw_actions}')
    created_tool_blocks = 0
    for seg in raw_actions:
        seg2 = seg if seg.endswith(')') else (seg + ')')
        logger.info(f'Seg2: {seg2}')
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
            # map to our computer tool input OR generic tool call
            tool_input: dict[str, Any] = {}
            f = (fname or '').lower()
            logger.info(f'F: {f}')

            # helpers for param aliasing
            def _first(*names: str) -> Any:
                for n in names:
                    if n in kwargs and kwargs[n] is not None:
                        return kwargs[n]
                return None

            def _center_from(*names: str) -> Any:
                val = _first(*names)
                return derive_center_coordinate(
                    val,
                    scale_from=(1920, 1080),
                    scale_to=(1024, 768),
                )

            # Accept both OG action names and our internal ones
            if f in {'click', 'left_single', 'left_click'}:
                center = _center_from(
                    'start_box', 'point', 'coordinate', 'position', 'at'
                )
                tool_input['action'] = 'left_click'
                if center:
                    tool_input['coordinate'] = center
            elif f in {'left_double', 'double_click'}:
                center = _center_from(
                    'start_box', 'point', 'coordinate', 'position', 'at'
                )
                tool_input['action'] = 'double_click'
                if center:
                    tool_input['coordinate'] = center
            elif f in {'right_single', 'right_click'}:
                center = _center_from(
                    'start_box', 'point', 'coordinate', 'position', 'at'
                )
                tool_input['action'] = 'right_click'
                if center:
                    tool_input['coordinate'] = center
            elif f in {'hover', 'mouse_move', 'move', 'cursor_move'}:
                center = _center_from(
                    'start_box', 'point', 'coordinate', 'position', 'at'
                )
                tool_input['action'] = 'mouse_move'
                if center:
                    tool_input['coordinate'] = center
            elif f in {'drag', 'select', 'left_click_drag', 'drag_and_drop'}:
                s = _center_from(
                    'start_box', 'start_point', 'from', 'start', 'point', 'coordinate'
                )
                e = _center_from('end_box', 'end_point', 'to', 'end', 'target')
                tool_input['action'] = 'left_click_drag'
                if s:
                    tool_input['coordinate'] = s
                if e:
                    tool_input['to'] = list(e)
            elif f in {
                'hotkey',
                'keypress',
                'key',
                'keydown',
                'keyup',
                'press_key',
                'key_down',
                'key_up',
            }:
                combo = _first('key', 'hotkey', 'combo', 'text')
                keys_list = kwargs.get('keys')
                if not combo and isinstance(keys_list, list) and keys_list:
                    combo = '+'.join(str(k) for k in keys_list)
                tool_input['action'] = 'key'
                if isinstance(combo, str) and combo:
                    tool_input['text'] = normalize_key_combo(combo)
            elif f in {'type', 'type_text', 'enter_text', 'input_text'}:
                txt = _first('content', 'text', 'value', 'string') or ''
                tool_input['action'] = 'type'
                if isinstance(txt, str):
                    tool_input['text'] = txt
            elif f in {'scroll', 'wheel', 'mousewheel'}:
                direction = str(_first('direction', 'dir') or '').lower()
                # amount in wheel notches if provided
                amount = _first(
                    'scroll_amount',
                    'amount',
                    'distance',
                    'delta',
                    'dy',
                    'delta_y',
                    'scroll_y',
                )
                try:
                    scroll_amount = int(amount) if amount is not None else 5
                except Exception:
                    scroll_amount = 5
                center = _center_from(
                    'start_box', 'point', 'coordinate', 'position', 'at'
                )
                # derive direction from dx/dy if not explicitly provided
                if not direction:
                    dx = _first('dx', 'delta_x', 'scroll_x')
                    dy = _first('dy', 'delta_y', 'scroll_y')
                    try:
                        if dy is not None and abs(int(dy)) >= (
                            abs(int(dx)) if dx is not None else 0
                        ):
                            direction = 'down' if int(dy) > 0 else 'up'
                            scroll_amount = abs(int(dy))
                        elif dx is not None:
                            direction = 'right' if int(dx) > 0 else 'left'
                            scroll_amount = abs(int(dx))
                    except Exception:
                        direction = direction  # keep as is
                tool_input['action'] = 'scroll'
                if direction in {'up', 'down', 'left', 'right'}:
                    tool_input['scroll_direction'] = direction
                tool_input['scroll_amount'] = scroll_amount
                if center:
                    tool_input['coordinate'] = center
            elif f in {'wait', 'sleep', 'pause', 'delay'}:
                ms = _first('ms', 'milliseconds', 'duration_ms')
                seconds = _first('seconds', 'secs', 's', 'duration', 'time')
                duration: float = 1.0
                try:
                    if ms is not None:
                        duration = float(ms) / 1000.0
                    elif seconds is not None:
                        duration = float(seconds)
                except Exception:
                    duration = 1.0
                tool_input['action'] = 'wait'
                tool_input['duration'] = duration
            elif f in {'finished'}:
                fin = kwargs.get('content') or kwargs.get('text') or kwargs.get('value')
                if isinstance(fin, str) and fin:
                    content_blocks.append(BetaTextBlockParam(type='text', text=fin))
                continue
            else:
                # Generic function-call fallback: treat function name as tool name
                # and kwargs as tool input. This enables dynamic tools from
                # internal_spec() to be used with UITARS textual actions.
                content_blocks.append(
                    BetaToolUseBlockParam(
                        type='tool_use',
                        id=f'uitars_call_{created_tool_blocks}',
                        name=str(fname or 'unknown_tool'),
                        input=kwargs,
                    )
                )
                created_tool_blocks += 1
                continue

            # If we mapped to the computer tool, emit that tool use
            content_blocks.append(
                BetaToolUseBlockParam(
                    type='tool_use',
                    id=f'uitars_call_{created_tool_blocks}',
                    name='computer',
                    input=tool_input,
                )
            )
            created_tool_blocks += 1
        except Exception:
            continue

    stop_reason = (
        'tool_use'
        if any(cb.get('type') == 'tool_use' for cb in content_blocks)
        else 'end_turn'
    )
    return content_blocks, stop_reason
