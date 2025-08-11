"""
UITARS provider handler implementation.

This handler integrates UI-TARS/Doubao-style GUI agent outputs that follow a
"Thought:/Action:" textual format and converts them into Anthropic-format
content blocks and tool_use inputs compatible with our existing `computer`
tool execution pipeline.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Optional, cast

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection, ToolResult
from server.computer_use.utils import (
    _make_api_tool_result,
    normalize_key_combo,
    derive_center_coordinate,
)
from server.settings import settings


# Prompt template adapted for Doubao/UITARS style agents
COMPUTER_USE_DOUBAO = (
    """
You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

Output Format:
Thought: ...\nAction: ...

Action Space:
click(point='<point>x1 y1</point>')
left_double(point='<point>x1 y1</point>')
right_single(point='<point>x1 y1</point>')
drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
hotkey(key='ctrl c')  # Split keys with a space and use lowercase. Do not use more than 3 keys in one hotkey action.
type(content='xxx')   # Use escape characters \\' , \\\" , and \\n in content. Use \\n to submit input.
scroll(point='<point>x1 y1</point>', direction='down or up or right or left')
wait()
finished(content='xxx')

Notes:
- Use English in Thought.
- Write a small plan and summarize your next action with its target element.
"""
).strip()


class UITARSHandler(BaseProviderHandler):
    """
    Handler for UITARS-like providers that return text with Thought/Action lines.

    It calls an OpenAI-compatible Chat Completions endpoint, then parses the
    textual Action into our `computer` tool actions.
    """

    def __init__(
        self,
        model: str = 'tgi',
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,
        tenant_schema: Optional[str] = None,
        image_truncation_threshold: int = 1,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            token_efficient_tools_beta=token_efficient_tools_beta,
            only_n_most_recent_images=only_n_most_recent_images,
            enable_prompt_caching=False,
            tenant_schema=tenant_schema,
            **kwargs,
        )
        self.model = model
        self.image_truncation_threshold = image_truncation_threshold

    async def initialize_client(self, api_key: str, **kwargs: Any) -> AsyncOpenAI:
        """Initialize an OpenAI-compatible client.

        Uses tenant-specific base URL and API key if available:
        - UITARS_BASE_URL
        - UITARS_API_KEY
        Fallbacks to provided api_key and default base_url.
        """
        # Reload settings to pick up latest env
        settings.__init__()

        # base_url = (
        #     self.tenant_setting('UITARS_BASE_URL')
        #     or getattr(settings, 'UITARS_BASE_URL', None)
        # )
        # key = self.tenant_setting('UITARS_API_KEY') or api_key

        base_url = 'http://147.189.203.65:8000/v1/'
        key = 'sk-1234567890'

        if base_url:
            logger.info(f'UITARS using custom base_url: {base_url}')
            return AsyncOpenAI(api_key=key, base_url=base_url)
        return AsyncOpenAI(api_key=key)

    def prepare_system(self, system_prompt: str) -> str:
        """Append UITARS-specific instructions to the base system prompt."""
        parts = [p for p in [system_prompt.strip(), COMPUTER_USE_DOUBAO] if p]
        return '\n\n'.join(parts)

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[ChatCompletionMessageParam]:
        """
        Convert Anthropic-format messages to OpenAI Chat Completions format.
        We do not use function tools; the model emits textual actions.
        """
        # Optionally trim older images for efficiency
        if self.only_n_most_recent_images:
            from server.computer_use.utils import _maybe_filter_to_n_most_recent_images

            _maybe_filter_to_n_most_recent_images(
                messages,
                self.only_n_most_recent_images,
                min_removal_threshold=self.image_truncation_threshold,
            )

        provider_messages: list[ChatCompletionMessageParam] = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content')

            if isinstance(content, str):
                # Collapse assistant text as user-visible context; provider often expects user/assistant only
                if role == 'user':
                    provider_messages.append(
                        cast(
                            ChatCompletionUserMessageParam,
                            {'role': 'user', 'content': cast(str, content)},
                        )
                    )
                else:
                    provider_messages.append(
                        cast(
                            ChatCompletionUserMessageParam,
                            {
                                'role': 'user',
                                'content': f'Assistant said: {cast(str, content)}',
                            },
                        )
                    )
            elif isinstance(content, list):
                parts: list[ChatCompletionContentPartParam] = []
                # Include text parts and base64 images as data URLs
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
                        # Flatten tool result text and image into user content for visibility
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
                                            'url': f'data:image/png;base64,{image_data}',
                                        },
                                    },
                                )
                            )

                if parts:
                    provider_messages.append(
                        cast(
                            ChatCompletionUserMessageParam,
                            {'role': 'user', 'content': parts},
                        )
                    )

        logger.info(
            f'Converted {len(messages)} messages to {len(provider_messages)} UITARS provider messages'
        )
        return provider_messages

    def prepare_tools(self, tool_collection: ToolCollection) -> list[Any]:
        """No tool schema is sent; the model emits textual actions."""
        return []

    async def call_api(
        self,
        client: AsyncOpenAI,
        messages: list[ChatCompletionMessageParam],
        system: str,
        tools: list[Any],  # unused
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> tuple[ChatCompletion, httpx.Request, httpx.Response]:
        logger.info('=== UITARS API Call ===')
        logger.info(f'Model: {model}')
        logger.info(f'Tenant schema: {self.tenant_schema}')
        # Prepend system prompt
        full_messages: list[ChatCompletionMessageParam] = []
        if system:
            sys_msg: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': system,
            }
            full_messages.append(sys_msg)
        full_messages.extend(messages)

        # log the full_messages
        logger.info(f'Full messages: {full_messages}')

        # TODO: use instructor
        response = await client.chat.completions.with_raw_response.create(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        parsed = response.parse()
        return parsed, response.http_response.request, response.http_response

    def convert_from_provider_response(
        self, response: ChatCompletion
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Parse the textual Thought/Action into Anthropic content blocks.
        Creates BetaToolUseBlockParam blocks that our sampling loop will execute.
        """
        content_blocks: list[BetaContentBlockParam] = []
        message = response.choices[0].message
        raw_text = message.content or ''

        # Extract Thought
        thought = None
        m = re.search(r'Thought:\s*(.+?)(?=\n\s*Action:|\Z)', raw_text, re.S)
        if m:
            thought = m.group(1).strip()
            if thought:
                content_blocks.append(BetaTextBlockParam(type='text', text=thought))

        # Extract Action payload
        action_str = ''
        am = re.search(r'Action:\s*(.+)\Z', raw_text, re.S)
        if am:
            action_str = am.group(1).strip()

        if not action_str:
            # No action; end turn
            return content_blocks, 'end_turn'

        # Some models return multiple actions separated by blank lines
        raw_actions = [
            seg.strip() for seg in re.split(r'\)\s*\n\s*\n', action_str) if seg.strip()
        ]
        parsed_actions: list[dict[str, Any]] = []
        for seg in raw_actions:
            seg2 = seg if seg.endswith(')') else (seg + ')')
            try:
                node = ast.parse(seg2, mode='eval')
                if not isinstance(node, ast.Expression) or not isinstance(
                    node.body, ast.Call
                ):
                    continue
                call = cast(ast.Call, node.body)
                # Function name
                if isinstance(call.func, ast.Name):
                    fname = call.func.id
                elif isinstance(call.func, ast.Attribute):
                    fname = call.func.attr
                else:
                    fname = ''
                # Keyword args
                kwargs: dict[str, Any] = {}
                for kw in call.keywords:
                    key = kw.arg or ''
                    val: Any
                    if isinstance(kw.value, ast.Constant):
                        val = kw.value.value
                    elif isinstance(kw.value, ast.Str):  # type: ignore[attr-defined]
                        val = kw.value.s  # py<3.8 compatibility
                    else:
                        # Fallback to source slice
                        val = seg2[kw.value.col_offset : kw.value.end_col_offset]  # type: ignore[attr-defined]
                    kwargs[key] = val
                parsed_actions.append({'function': fname, 'args': kwargs})
            except Exception as e:  # pragma: no cover
                logger.warning(f'UITARS failed to parse action segment: {seg2} ({e})')

        def _center_from_box(val: Any) -> Optional[tuple[int, int]]:
            return derive_center_coordinate(val)

        def _normalize_key_combo(combo: str) -> str:
            return normalize_key_combo(combo)

        created_tool_blocks = 0
        for pa in parsed_actions:
            atype = (pa.get('function') or '').lower()
            args = pa.get('args') or {}

            tool_input: dict[str, Any] = {}
            if atype in {'click', 'left_single'}:
                center = _center_from_box(args.get('start_box') or args.get('point'))
                tool_input['action'] = 'left_click'
                if center:
                    tool_input['coordinate'] = center
            elif atype in {'left_double'}:
                center = _center_from_box(args.get('start_box') or args.get('point'))
                tool_input['action'] = 'double_click'
                if center:
                    tool_input['coordinate'] = center
            elif atype in {'right_single'}:
                center = _center_from_box(args.get('start_box') or args.get('point'))
                tool_input['action'] = 'right_click'
                if center:
                    tool_input['coordinate'] = center
            elif atype in {'hover'}:
                center = _center_from_box(args.get('start_box') or args.get('point'))
                tool_input['action'] = 'mouse_move'
                if center:
                    tool_input['coordinate'] = center
            elif atype in {'drag', 'select'}:
                s = _center_from_box(args.get('start_box') or args.get('start_point'))
                e = _center_from_box(args.get('end_box') or args.get('end_point'))
                tool_input['action'] = 'left_click_drag'
                if s:
                    tool_input['coordinate'] = s
                if e:
                    tool_input['to'] = list(e)
            elif atype in {'hotkey', 'keypress', 'key', 'keydown'}:
                combo = args.get('key') or args.get('hotkey') or ''
                tool_input['action'] = 'key'
                if isinstance(combo, str) and combo:
                    tool_input['text'] = _normalize_key_combo(combo)
            elif atype in {'release', 'keyup'}:
                combo = args.get('key') or ''
                tool_input['action'] = 'key'
                if isinstance(combo, str) and combo:
                    tool_input['text'] = _normalize_key_combo(combo)
            elif atype in {'type'}:
                txt = args.get('content') or ''
                tool_input['action'] = 'type'
                if isinstance(txt, str):
                    tool_input['text'] = txt
            elif atype in {'scroll'}:
                direction = (args.get('direction') or '').lower()
                center = _center_from_box(args.get('start_box') or args.get('point'))
                tool_input['action'] = 'scroll'
                if direction in {'up', 'down', 'left', 'right'}:
                    tool_input['scroll_direction'] = direction
                # Provide a modest default amount in wheel notches
                tool_input['scroll_amount'] = 5
                if center:
                    tool_input['coordinate'] = center
            elif atype in {'wait'}:
                tool_input['action'] = 'wait'
                tool_input['duration'] = 1.0
            elif atype in {'finished'}:
                # Treat as end of turn with a summary text
                fin = args.get('content')
                if isinstance(fin, str) and fin:
                    content_blocks.append(BetaTextBlockParam(type='text', text=fin))
                continue
            else:
                # Unknown action -> ask for screenshot to continue
                tool_input['action'] = 'screenshot'

            tool_use_block = BetaToolUseBlockParam(
                type='tool_use',
                id=f'uitars_call_{created_tool_blocks}',
                name='computer',
                input=tool_input,
            )
            created_tool_blocks += 1
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
