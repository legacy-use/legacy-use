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
    summarize_openai_chat,
    summarize_beta_blocks,
)
from server.computer_use.converters import (
    beta_messages_to_openai_chat,
    chat_completion_text_to_blocks,
)
from server.settings import settings


# Prompt template adapted for Doubao/UITARS style agents
COMPUTER_USE_DOUBAO = (
    """
You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

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

## Notes:
- Use English in `Thought`.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.
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
        logger.info(f'Model: {model}, Tenant schema: {self.tenant_schema}')
        logger.info(f'Input summary: {summarize_openai_chat(messages)}')
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
        blocks, _ = chat_completion_text_to_blocks(
            parsed.choices[0].message.content or ''
        )
        logger.info(f'Output summary: {summarize_beta_blocks(blocks)}')
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
