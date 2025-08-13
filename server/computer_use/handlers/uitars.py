"""
UITARS provider handler implementation.

This handler integrates UI-TARS/Doubao-style GUI agent outputs that follow a
"Thought:/Action:" textual format and converts them into Anthropic-format
content blocks and tool_use inputs compatible with our existing `computer`
tool execution pipeline.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaToolResultBlockParam,
)

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection, ToolResult
from server.computer_use.utils import (
    _make_api_tool_result,
)
from server.computer_use.handlers.converter_utils import (
    beta_messages_to_openai_chat,
    chat_completion_text_to_blocks,
)
from server.settings import settings
from server.computer_use.config import APIProvider


# Prompt template adapted for Doubao/UITARS style agents
COMPUTER_USE_DOUBAO = (
    """
You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Output Format
```
Thought: ...
Action: ...
```

## Notes:
- Use English in `Thought`.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.
"""
).strip()

COMPUTER_USE_DOUBAO_MOCK = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Output Format
```
Thought: ...
Action: ...
```

## Action Space

click(point='<point>x1 y1</point>')
left_double(point='<point>x1 y1</point>')
right_single(point='<point>x1 y1</point>')
drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
hotkey(key='ctrl c') # Split keys with a space and use lowercase. Also, do not use more than 3 keys in one hotkey action.
type(content='xxx') # Use escape characters \\', \\\", and \\n in content part to ensure we can parse the content in normal python string format. If you want to submit your input, use \\n at the end of content. 
scroll(point='<point>x1 y1</point>', direction='down or up or right or left') # Show more information on the `direction` side.
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.


## Note
- Use English in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
1. Open up the task manager, using the keyboard shortcut `Ctrl + Shift + Esc`
2. Click on the performance tab
3. Read out the metrics
4. Search for "Settings" in the task bar
5. List and return all serach entries mentioned
"""


class UITARSHandler(BaseProviderHandler):
    """
    Handler for UITARS-like providers that return text with Thought/Action lines.

    It calls an OpenAI-compatible Chat Completions endpoint, then parses the
    textual Action into our `computer` tool actions.
    """

    def __init__(
        self,
        provider: APIProvider = APIProvider.UITARS,
        model: str = 'tgi',
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,
        tenant_schema: Optional[str] = None,
        image_truncation_threshold: int = 1,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            token_efficient_tools_beta=token_efficient_tools_beta,
            only_n_most_recent_images=only_n_most_recent_images,
            enable_prompt_caching=False,
            tenant_schema=tenant_schema,
            max_retries=max_retries,
            **kwargs,
        )
        self.provider = provider
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

        # Try to get tenant-specific settings first
        base_url = self.tenant_setting('UITARS_BASE_URL') or getattr(
            settings, 'UITARS_BASE_URL', 'http://147.189.202.17:8000/v1/'
        )
        tenant_key = self.tenant_setting('UITARS_API_KEY') or getattr(
            settings, 'UITARS_API_KEY', None
        )
        final_api_key = tenant_key or api_key or 'sk-1234567890'

        logger.info(f'UITARS using base_url: {base_url}')
        return AsyncOpenAI(api_key=final_api_key, base_url=base_url)

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
        # Apply common preprocessing; UITARS supports multiple images; use handler threshold
        self.preprocess_messages(
            messages, image_truncation_threshold=self.image_truncation_threshold
        )
        provider_messages: list[ChatCompletionMessageParam] = (
            beta_messages_to_openai_chat(messages)
        )
        logger.info(
            f'Converted {len(messages)} messages to {len(provider_messages)} UITARS provider messages'
        )
        return provider_messages

    def prepare_tools(self, tool_collection: ToolCollection) -> list[str]:
        """Build textual Action Space from provided tools' internal_spec().

        For any tool with an `actions` array in `internal_spec()`, we emit
        `toolName(action='action_name', param=...)` entries.
        For tools with only `input_schema`, we emit `toolName(param=...)` entries.
        """

        def placeholder_for(schema: dict) -> str:
            if not isinstance(schema, dict):
                return '...'
            if 'enum' in schema and isinstance(schema['enum'], list) and schema['enum']:
                v = schema['enum'][0]
                return f"'{v}'" if isinstance(v, str) else str(v)
            t = schema.get('type')
            if t == 'string':
                return "'text'"
            if t in ('integer', 'number'):
                return '0'
            if t == 'array':
                return '[]'
            if isinstance(t, str) and 'array[int,int]' in t:
                return '[x,y]'
            return '...'

        lines: list[str] = []

        for tool in tool_collection.tools:
            name = getattr(tool, 'name', None)
            if not name or not hasattr(tool, 'internal_spec'):
                continue
            try:
                spec = tool.internal_spec()  # type: ignore[attr-defined]
            except Exception:
                continue
            if not isinstance(spec, dict):
                continue

            # If the tool declares discrete actions
            actions = spec.get('actions')
            if isinstance(actions, list) and actions:
                for action in actions:
                    aname = str(action.get('name') or '')
                    params = action.get('params') or {}
                    parts = [f"action='{aname}'"]
                    if isinstance(params, dict):
                        for p, pschema in params.items():
                            parts.append(f'{p}={placeholder_for(pschema)}')
                    lines.append(f'{name}({", ".join(parts)})')
                continue

            # Otherwise, use input_schema
            schema = spec.get('input_schema') or {}
            properties = schema.get('properties') if isinstance(schema, dict) else {}
            parts: list[str] = []
            if isinstance(properties, dict):
                for p, pschema in properties.items():
                    parts.append(f'{p}={placeholder_for(pschema)}')
            lines.append(f'{name}({", ".join(parts)})')

        # Always allow finish
        lines.append("finished(content='...')")
        return lines

    async def call_api(
        self,
        client: AsyncOpenAI,
        messages: list[ChatCompletionMessageParam],
        system: str,
        tools: list[str],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> tuple[ChatCompletion, httpx.Request, httpx.Response]:
        # Build action space section if tools are available
        if tools:
            system = f'{system}\n\n## Action Space\n\n' + '\n'.join(tools)

        full_messages: list[ChatCompletionMessageParam] = []
        if system:
            sys_msg: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': system,
            }
            full_messages.append(sys_msg)

        full_messages.extend(messages)

        # Log truncated messages for debugging
        logger.debug(f'Sending {len(full_messages)} messages to UITARS')

        response = await client.chat.completions.with_raw_response.create(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        parsed = response.parse()
        logger.debug(
            f'UITARS response: {parsed.choices[0].message.content[:200] if parsed.choices and parsed.choices[0].message.content else "(empty)"}'
        )
        return parsed, response.http_response.request, response.http_response

    def convert_from_provider_response(
        self, response: ChatCompletion
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Parse the textual Thought/Action into Anthropic content blocks.
        Creates BetaToolUseBlockParam blocks that our sampling loop will execute.
        """
        message = response.choices[0].message
        raw_text = message.content or ''
        return chat_completion_text_to_blocks(raw_text)

    async def execute(
        self,
        client: AsyncOpenAI,
        messages: list[BetaMessageParam],
        system: str,
        tools: ToolCollection,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        """
        Make API call to UITARS and return standardized response format.

        This is the public interface that calls the raw API and converts the response.
        """
        # Convert inputs to provider format
        provider_messages = self.convert_to_provider_messages(messages)
        system_str = self.prepare_system(system)
        tool_actions = self.prepare_tools(tools)

        # Call the raw API
        parsed_response, request, raw_response = await self.call_api(
            client=client,
            messages=provider_messages,
            system=system_str,
            tools=tool_actions,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        # Convert response to standardized format
        content_blocks, stop_reason = self.convert_from_provider_response(
            parsed_response
        )

        return content_blocks, stop_reason, request, raw_response

    def make_tool_result(
        self, result: ToolResult, tool_use_id: str
    ) -> BetaToolResultBlockParam:
        return _make_api_tool_result(result, tool_use_id)
