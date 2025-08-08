"""
OpenAI CUA (Computer-Using Agent) provider handler implementation.

This handler uses OpenAI's Responses API with the built-in `computer_use_preview` tool
and maps its output to our Anthropic-format content blocks and tool_use inputs
for execution by our existing `computer` tool.
"""

from typing import Any, Optional, cast
import json

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection, ToolResult
from server.computer_use.utils import _make_api_tool_result

from openai import AsyncOpenAI
from openai.types.responses import (
    ToolParam,
    ComputerToolParam,
    FunctionToolParam,
    ResponseInputParam,
    Response,
)
from openai.types.responses.easy_input_message_param import EasyInputMessageParam


class OpenAICUAHandler(BaseProviderHandler):
    """
    Handler for OpenAI Responses API with `computer_use_preview` tool.
    """

    def __init__(
        self,
        model: str = 'computer-use-preview',
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,  # Will be ignored
        **kwargs,
    ):
        super().__init__(
            token_efficient_tools_beta=token_efficient_tools_beta,
            only_n_most_recent_images=1,  # computer-use-preview only supports 1 image
            enable_prompt_caching=False,
            **kwargs,
        )
        self.model = model

    async def initialize_client(self, api_key: str, **kwargs) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=api_key)

    def prepare_system(self, system_prompt: str) -> str:
        # TODO: Remove, and find solution on how openAI can keep track on state of current job
        openai_instructions = """
        Keep meta information in your summary about where you are in the step by step guide. Keep also information about relevant information you extracted.
        Feel free to include additional information in your summary. There is no need to be short or concise.
"""
        return system_prompt + '\n\n' + openai_instructions

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> ResponseInputParam:
        """
        Convert Anthropic-format messages to OpenAI Responses API `input` format:
        a list of objects with {role: 'user', content: [{type: input_text|input_image, ...}]}.
        """
        if self.only_n_most_recent_images:
            from server.computer_use.utils import _maybe_filter_to_n_most_recent_images

            _maybe_filter_to_n_most_recent_images(
                messages, self.only_n_most_recent_images, min_removal_threshold=1
            )

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
                                'content': [
                                    {'type': 'input_text', 'text': cast(str, content)}
                                ],
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
                                    'detail': 'auto',
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
                                    'detail': 'auto',
                                    'image_url': f'data:image/png;base64,{image_data}',
                                }
                            )

                if input_parts:
                    provider_messages.append(
                        cast(
                            EasyInputMessageParam,
                            {'role': 'user', 'content': input_parts},
                        )
                    )

        logger.info(
            f'Converted to {len(provider_messages)} OpenAI Responses input messages (CUA)'
        )
        return provider_messages

    def prepare_tools(self, tool_collection: ToolCollection) -> list[ToolParam]:
        """Replace `computer` tool with `computer_use_preview` and keep other tools in OpenAI format.

        - Extract display settings from the Anthropic `computer` tool if present
        - Exclude the `computer` tool from the OpenAI tools list
        - Include `computer_use_preview` tool definition for the Responses API
        - Map all other tools via their `to_openai_tool()` adapters
        """
        display_width = 1024
        display_height = 768
        environment = 'windows'

        openai_tools: list[Any] = []

        # Collect non-computer tools and capture display settings from computer tool
        try:
            for tool in tool_collection.tools:
                if getattr(tool, 'name', None) == 'computer':
                    display_width = getattr(tool, 'width', display_width)
                    display_height = getattr(tool, 'height', display_height)
                    # Do NOT add the computer tool; replaced by computer_use_preview
                    continue
                # Map other tools to OpenAI function tools
                try:
                    openai_tools.append(tool.to_openai_tool())
                except Exception:
                    # If mapping fails for a tool, skip it rather than failing entirely
                    logger.exception('Failed to convert tool to OpenAI format')
        except Exception:  # pragma: no cover
            # If anything unexpected happens while iterating tools, fall back to only preview tool
            logger.exception(
                'Error preparing OpenAI CUA tools; falling back to preview only'
            )

        # Add the computer_use_preview tool
        preview_tool: ComputerToolParam = {
            'type': 'computer_use_preview',
            'display_width': display_width,
            'display_height': display_height,
            'environment': environment,
        }

        # Flatten function tools to Responses API tool schema: require top-level name/parameters
        flattened_tools: list[FunctionToolParam] = []
        for t in openai_tools:
            if t['type'] == 'function':
                fn = t['function']
                flattened_tools.append(
                    {
                        'type': 'function',
                        'name': str(fn.get('name') or ''),
                        'description': str(fn.get('description') or ''),
                        'strict': False,  # TODO determent if True is better
                        'parameters': fn.get('parameters')
                        or {
                            'type': 'object',
                            'properties': {},
                        },
                    }
                )

        tools_result: list[ToolParam] = [preview_tool, *flattened_tools]
        logger.debug(
            f'OpenAI CUA tools prepared: preview + '
            f'{[t.get("name") if t.get("type") == "function" else t.get("type") for t in flattened_tools]}'
        )
        return tools_result

    async def call_api(
        self,
        client: AsyncOpenAI,
        messages: ResponseInputParam,
        system: str,
        tools: list[ToolParam],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[Response, httpx.Request, httpx.Response]:
        logger.info('=== OpenAI CUA API Call ===')
        logger.info(f'Model: {model}')
        logger.info(f'Tools: {tools}')
        logger.info(f'Tenant schema: {self.tenant_schema}')
        logger.debug(f'Max tokens: {max_tokens}, Temperature: {temperature}')

        # Print input, but hide large base64 images if present
        for item in messages:
            try:
                if isinstance(item, dict):
                    content = item.get('content')
                    if isinstance(content, list) and content:
                        first = content[0]
                        if (
                            isinstance(first, dict)
                            and first.get('type') == 'input_image'
                        ):
                            continue
                logger.info(f'Input message: {item}')
            except Exception:
                logger.info(f'Input message: {item}')

        response = await client.responses.with_raw_response.create(
            model=model,
            input=messages,
            tools=tools,
            reasoning={'summary': 'concise'},
            truncation='auto',
            instructions=system if system else None,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        parsed_response = response.parse()
        logger.info(f'Parsed response: {parsed_response}')

        return parsed_response, response.http_response.request, response.http_response

    def convert_from_provider_response(
        self, response: Response
    ) -> tuple[list[BetaContentBlockParam], str]:
        """Convert Responses API output to Anthropic blocks and stop reason."""
        content_blocks: list[BetaContentBlockParam] = []

        output_items = getattr(response, 'output', None) or []
        logger.info(
            f'OpenAI Responses output items: {len(output_items)} (CUA preview mode)'
        )

        def _get(obj: Any, key: str, default: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        def map_action_to_tool_input(action: Any) -> dict:
            atype = _get(action, 'type')
            mapped: dict[str, Any] = {}

            def _normalize_key_combo(combo: str) -> str:
                if not isinstance(combo, str):
                    return combo  # type: ignore[return-value]
                parts = [
                    p.strip() for p in combo.replace(' ', '').split('+') if p.strip()
                ]
                alias_map = {
                    'esc': 'Escape',
                    'escape': 'Escape',
                    'enter': 'Return',
                    'return': 'Return',
                    'win': 'Super_L',
                    'windows': 'Super_L',
                    'super': 'Super_L',
                    'meta': 'Super_L',
                    'cmd': 'Super_L',
                    'backspace': 'BackSpace',
                    'del': 'Delete',
                    'delete': 'Delete',
                    'tab': 'Tab',
                    'space': 'space',
                    'pageup': 'Page_Up',
                    'pagedown': 'Page_Down',
                    'home': 'Home',
                    'end': 'End',
                    'up': 'Up',
                    'down': 'Down',
                    'left': 'Left',
                    'right': 'Right',
                    'printscreen': 'Print',
                    'prtsc': 'Print',
                    'ctrl': 'ctrl',
                    'control': 'ctrl',
                    'shift': 'shift',
                    'alt': 'alt',
                }

                def normalize_part(p: str) -> str:
                    low = p.lower()
                    if low in alias_map:
                        return alias_map[low]
                    if low.startswith('f') and low[1:].isdigit():
                        return f'F{int(low[1:])}'
                    if len(p) == 1:
                        return p
                    return p

                normalized = [normalize_part(p) for p in parts]
                return '+'.join(normalized)

            if atype == 'click':
                button = _get(action, 'button', 'left')
                x = _get(action, 'x')
                y = _get(action, 'y')
                if button == 'left':
                    mapped['action'] = 'left_click'
                elif button == 'right':
                    mapped['action'] = 'right_click'
                elif button == 'middle':
                    mapped['action'] = 'middle_click'
                else:
                    mapped['action'] = 'left_click'
                if isinstance(x, int) and isinstance(y, int):
                    mapped['coordinate'] = (x, y)
                logger.info(f'CUA map_action: click -> {mapped}')
            elif atype == 'double_click':
                x = _get(action, 'x')
                y = _get(action, 'y')
                mapped['action'] = 'double_click'
                if isinstance(x, int) and isinstance(y, int):
                    mapped['coordinate'] = (x, y)
                logger.info(f'CUA map_action: double_click -> {mapped}')
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
                logger.info(f'CUA map_action: scroll -> {mapped}')
            elif atype == 'type':
                mapped['action'] = 'type'
                text_val = _get(action, 'text')
                if text_val is not None:
                    mapped['text'] = text_val
                logger.info(f'CUA map_action: type -> {mapped}')
            elif atype in ('keypress', 'key', 'key_event'):
                # Map keypress to our 'key' action using a normalized combo string
                keys = _get(action, 'keys')
                key = _get(action, 'key')
                combo = None
                if isinstance(keys, list) and keys:
                    combo = '+'.join(str(k) for k in keys)
                elif isinstance(key, str):
                    combo = key
                if combo:
                    mapped['action'] = 'key'
                    mapped['text'] = _normalize_key_combo(combo)
                else:
                    # Fallback to screenshot if nothing usable
                    mapped['action'] = 'screenshot'
                logger.info(f'CUA map_action: keypress -> {mapped}')
            elif atype == 'wait':
                mapped['action'] = 'wait'
                ms = _get(action, 'ms') or _get(action, 'duration_ms')
                try:
                    mapped['duration'] = (float(ms) / 1000.0) if ms is not None else 1.0
                except Exception:
                    mapped['duration'] = 1.0
                logger.info(f'CUA map_action: wait -> {mapped}')
            elif atype == 'screenshot':
                mapped['action'] = 'screenshot'
                logger.info('CUA map_action: screenshot')
            elif atype == 'cursor_position':
                x = _get(action, 'x')
                y = _get(action, 'y')
                mapped['action'] = 'mouse_move'
                if isinstance(x, int) and isinstance(y, int):
                    mapped['coordinate'] = (x, y)
                logger.info(f'CUA map_action: cursor_position -> {mapped}')
            else:
                mapped['action'] = 'screenshot'
                logger.info(f'CUA map_action: unknown {atype} -> screenshot')
            return mapped

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
                    tool_input = map_action_to_tool_input(action)
                except Exception:
                    # Fallback to a basic screenshot action
                    tool_input = {'action': 'screenshot'}
                tool_use_block = BetaToolUseBlockParam(
                    type='tool_use',
                    id=_get(item, 'id') or _get(item, 'call_id') or 'call_0',
                    name='computer',
                    input=tool_input,
                )
                content_blocks.append(tool_use_block)
            elif itype in ('tool_call', 'function_call'):
                # Generic function tool call from Responses API
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
                        logger.exception(
                            'Failed to parse tool_call arguments; using empty dict'
                        )
                        tool_input = {}
                elif isinstance(raw_args, dict):
                    tool_input = raw_args
                # Tool-specific adjustments
                if tool_name == 'extraction' and 'data' not in tool_input:
                    if 'name' in tool_input and 'result' in tool_input:
                        original_input = tool_input.copy()
                        tool_input = {
                            'data': {
                                'name': original_input['name'],
                                'result': original_input['result'],
                            }
                        }
                        logger.info(
                            f"Wrapped extraction tool input into 'data': from {original_input} to {tool_input}"
                        )
                tool_use_block = BetaToolUseBlockParam(
                    type='tool_use', id=call_id, name=tool_name, input=tool_input
                )
                content_blocks.append(tool_use_block)

        has_tool_use = any(cb.get('type') == 'tool_use' for cb in content_blocks)
        # If OpenAI emitted computer_call but we somehow produced no tool_use blocks, still continue the loop
        stop_reason = (
            'tool_use' if (has_tool_use or found_computer_call) else 'end_turn'
        )
        return content_blocks, stop_reason

    def parse_tool_use(self, content_block: BetaContentBlockParam) -> Optional[dict]:
        if content_block.get('type') == 'tool_use':
            return {
                'name': content_block.get('name'),
                'id': content_block.get('id'),
                'input': content_block.get('input'),
            }
        return None

    def make_tool_result(
        self, result: ToolResult, tool_use_id: str
    ) -> BetaToolResultBlockParam:
        return _make_api_tool_result(result, tool_use_id)
