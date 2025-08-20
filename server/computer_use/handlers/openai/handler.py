"""
OpenAI provider handler implementation (modularized).

This module contains the handler class and delegates conversion logic
to helper modules for readability and maintainability.
"""

from typing import Any, Optional

import httpx
import instructor
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
)
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolParam,
)

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.handlers.utils.converter_utils import (
    internal_specs_to_openai_chat_functions,
)
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection

from .message_converter import convert_to_openai_messages
from .response_converter import convert_from_openai_response


class OpenAIHandler(BaseProviderHandler):
    """Handler for OpenAI API provider."""

    COMPUTER_ACTIONS = {
        'screenshot',
        'left_click',
        'mouse_move',
        'type',
        'key',
        'scroll',
        'left_click_drag',
        'right_click',
        'middle_click',
        'double_click',
        'triple_click',
        'left_mouse_down',
        'left_mouse_up',
        'hold_key',
        'wait',
    }

    STOP_REASON_MAP = {
        'stop': 'end_turn',
        'tool_calls': 'tool_use',
        'length': 'max_tokens',
    }

    def __init__(
        self,
        model: str,
        tenant_schema: str,
        only_n_most_recent_images: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(
            tenant_schema=tenant_schema,
            only_n_most_recent_images=only_n_most_recent_images,
            **kwargs,
        )
        self.model = model

    async def initialize_client(
        self, api_key: str, **kwargs
    ) -> instructor.AsyncInstructor:
        tenant_key = self.tenant_setting('OPENAI_API_KEY')
        final_api_key = tenant_key or api_key
        if not final_api_key:
            raise ValueError(
                'OpenAI API key is required. Please provide either '
                'OPENAI_API_KEY tenant setting or api_key parameter.'
            )
        openai_client = AsyncOpenAI(api_key=final_api_key)
        return instructor.from_openai(openai_client, max_retries=self.max_retries)

    def prepare_system(self, system_prompt: str) -> str:
        return system_prompt

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[ChatCompletionMessageParam]:
        messages = self.preprocess_messages(messages)
        return convert_to_openai_messages(messages)

    def prepare_tools(
        self, tool_collection: ToolCollection
    ) -> list[ChatCompletionToolParam]:
        tools: list[ChatCompletionToolParam] = internal_specs_to_openai_chat_functions(
            list(tool_collection.tools)
        )
        logger.debug(
            f'OpenAI tools after conversion: {[t.get("function", {}).get("name") for t in tools]}'
        )
        return tools

    async def make_ai_request(
        self,
        client: instructor.AsyncInstructor,
        messages: list[ChatCompletionMessageParam],
        system: str,
        tools: list[ChatCompletionToolParam],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> tuple[ChatCompletion, httpx.Request, httpx.Response]:
        full_messages: list[ChatCompletionMessageParam] = []
        if system:
            sys_msg: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': system,
            }
            full_messages.append(sys_msg)
        full_messages.extend(messages)

        logger.debug(f'Messages: {self._truncate_for_debug(full_messages)}')

        params: dict[str, Any] = dict(
            model=model,
            messages=full_messages,
            tools=tools,
        )
        if model.lower().startswith('gpt-5'):
            params['max_completion_tokens'] = max_tokens
        else:
            params['max_tokens'] = max_tokens
            params['temperature'] = temperature

        response = await client.beta.chat.completions.with_raw_response.create(**params)

        parsed_response = response.parse()
        logger.debug(f'Parsed response: {parsed_response}')

        return (
            parsed_response,
            response.http_response.request,
            response.http_response,
        )

    async def execute(
        self,
        client: instructor.AsyncInstructor,
        messages: list[BetaMessageParam],
        system: str,
        tools: ToolCollection,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        openai_messages = self.convert_to_provider_messages(messages)
        system_str = self.prepare_system(system)
        openai_tools = self.prepare_tools(tools)

        parsed_response, request, raw_response = await self.make_ai_request(
            client=client,
            messages=openai_messages,
            system=system_str,
            tools=openai_tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        content_blocks, stop_reason = self.convert_from_provider_response(
            parsed_response
        )

        return content_blocks, stop_reason, request, raw_response

    def convert_from_provider_response(
        self, response: ChatCompletion
    ) -> tuple[list[BetaContentBlockParam], str]:
        return convert_from_openai_response(
            response, self.STOP_REASON_MAP, self.COMPUTER_ACTIONS
        )
