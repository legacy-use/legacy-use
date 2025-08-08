"""
OpenAI CUA (Computer-Using Agent) provider handler implementation.

This handler uses OpenAI's Responses API with the built-in `computer_use_preview` tool
and maps its output to our Anthropic-format content blocks and tool_use inputs
for execution by our existing `computer` tool.
"""

from typing import Any, Optional, cast

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


class OpenAICUAHandler(BaseProviderHandler):
    """
    Handler for OpenAI Responses API with `computer_use_preview` tool.
    """

    def __init__(
        self,
        model: str = 'computer-use-preview',
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(
            token_efficient_tools_beta=token_efficient_tools_beta,
            only_n_most_recent_images=only_n_most_recent_images,
            enable_prompt_caching=False,
            **kwargs,
        )
        self.model = model

    async def initialize_client(self, api_key: str, **kwargs) -> Any:
        return AsyncOpenAI(api_key=api_key)

    def prepare_system(self, system_prompt: str) -> str:
        return system_prompt

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[dict]:
        """
        Convert Anthropic-format messages to OpenAI Responses API `input` format:
        a list of objects with {role: 'user', content: [{type: input_text|input_image, ...}]}.
        """
        if self.only_n_most_recent_images:
            from server.computer_use.utils import _maybe_filter_to_n_most_recent_images

            _maybe_filter_to_n_most_recent_images(
                messages, self.only_n_most_recent_images, min_removal_threshold=1
            )

        provider_messages: list[dict] = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content')

            if isinstance(content, str):
                if role == 'user':
                    provider_messages.append(
                        {
                            'role': 'user',
                            'content': [
                                {'type': 'input_text', 'text': cast(str, content)}
                            ],
                        }
                    )
                else:
                    provider_messages.append(
                        {
                            'role': 'user',
                            'content': [
                                {
                                    'type': 'input_text',
                                    'text': f'Assistant said: {content}',
                                }
                            ],
                        }
                    )
            elif isinstance(content, list):
                input_parts: list[dict] = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get('type')
                    if btype == 'text':
                        text_val = block.get('text', '')
                        if text_val:
                            input_parts.append({'type': 'input_text', 'text': text_val})
                    elif btype == 'image':
                        source = block.get('source', {})
                        if source.get('type') == 'base64' and source.get('data'):
                            data_url = f'data:{source.get("media_type", "image/png")};base64,{source.get("data")}'
                            input_parts.append(
                                {'type': 'input_image', 'image_url': data_url}
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
                                {'type': 'input_text', 'text': text_content}
                            )
                        if image_data:
                            input_parts.append(
                                {
                                    'type': 'input_image',
                                    'image_url': f'data:image/png;base64,{image_data}',
                                }
                            )

                if input_parts:
                    provider_messages.append({'role': 'user', 'content': input_parts})

        logger.info(
            f'Converted to {len(provider_messages)} OpenAI Responses input messages (CUA)'
        )
        return provider_messages

    def prepare_tools(self, tool_collection: ToolCollection) -> list[dict]:
        """Return `computer_use_preview` tool specification for Responses API."""
        display_width = 1024
        display_height = 768
        environment = 'windows'
        try:
            for tool in tool_collection.tools:
                if getattr(tool, 'name', None) == 'computer':
                    display_width = getattr(tool, 'width', display_width)
                    display_height = getattr(tool, 'height', display_height)
                    break
        except Exception:  # pragma: no cover
            pass

        preview_tools = [
            {
                'type': 'computer_use_preview',
                'display_width': display_width,
                'display_height': display_height,
                'environment': environment,
            }
        ]
        logger.debug(f'OpenAI CUA preview tools: {preview_tools}')
        return preview_tools

    async def call_api(
        self,
        client: Any,
        messages: list[Any],
        system: str,
        tools: list[dict],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[Any, httpx.Request, httpx.Response]:
        logger.info('=== OpenAI CUA API Call ===')
        logger.info(f'Model: {model}')
        logger.info(f'Tenant schema: {self.tenant_schema}')
        logger.debug(f'Max tokens: {max_tokens}, Temperature: {temperature}')

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
        self, response: Any
    ) -> tuple[list[BetaContentBlockParam], str]:
        """Convert Responses API output to Anthropic blocks and stop reason."""
        content_blocks: list[BetaContentBlockParam] = []

        output_items = getattr(response, 'output', None) or []
        logger.info(
            f'OpenAI Responses output items: {len(output_items)} (CUA preview mode)'
        )

        def map_action_to_tool_input(action: dict) -> dict:
            atype = action.get('type')
            mapped: dict[str, Any] = {}
            if atype == 'click':
                button = action.get('button', 'left')
                x = action.get('x')
                y = action.get('y')
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
            elif atype == 'double_click':
                x = action.get('x')
                y = action.get('y')
                mapped['action'] = 'double_click'
                if isinstance(x, int) and isinstance(y, int):
                    mapped['coordinate'] = (x, y)
            elif atype == 'scroll':
                sx = int(action.get('scroll_x') or 0)
                sy = int(action.get('scroll_y') or 0)
                if abs(sy) >= abs(sx):
                    mapped['scroll_direction'] = 'down' if sy > 0 else 'up'
                    mapped['scroll_amount'] = abs(sy)
                else:
                    mapped['scroll_direction'] = 'right' if sx > 0 else 'left'
                    mapped['scroll_amount'] = abs(sx)
                mapped['action'] = 'scroll'
            elif atype == 'type':
                mapped['action'] = 'type'
                if 'text' in action:
                    mapped['text'] = action.get('text')
            elif atype == 'wait':
                mapped['action'] = 'wait'
                ms = action.get('ms') or action.get('duration_ms')
                try:
                    mapped['duration'] = (float(ms) / 1000.0) if ms is not None else 1.0
                except Exception:
                    mapped['duration'] = 1.0
            elif atype == 'screenshot':
                mapped['action'] = 'screenshot'
            elif atype == 'cursor_position':
                x = action.get('x')
                y = action.get('y')
                mapped['action'] = 'mouse_move'
                if isinstance(x, int) and isinstance(y, int):
                    mapped['coordinate'] = (x, y)
            else:
                mapped['action'] = 'screenshot'
            return mapped

        for item in output_items:
            if not isinstance(item, dict):
                continue
            itype = item.get('type')
            if itype == 'reasoning':
                summary_items = item.get('summary') or []
                for s in summary_items:
                    txt = s.get('text') if isinstance(s, dict) else None
                    if txt:
                        content_blocks.append(BetaTextBlockParam(type='text', text=txt))
            elif itype == 'computer_call':
                action = item.get('action') or {}
                tool_input = map_action_to_tool_input(action)
                tool_use_block = BetaToolUseBlockParam(
                    type='tool_use',
                    id=item.get('id') or item.get('call_id') or 'call_0',
                    name='computer',
                    input=tool_input,
                )
                content_blocks.append(tool_use_block)

        stop_reason = (
            'tool_use'
            if any(cb.get('type') == 'tool_use' for cb in content_blocks)
            else 'end_turn'
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
