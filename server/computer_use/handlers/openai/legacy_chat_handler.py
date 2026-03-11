"""
Legacy OpenAI provider handler implementation based on Chat Completions.
"""

from typing import Any

import instructor
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
)
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolParam,
)

from server.computer_use.handlers.base import ProviderExecutionResult
from server.computer_use.handlers.utils.converter_utils import (
    internal_specs_to_openai_chat_functions,
)
from server.computer_use.logging import logger
from server.computer_use.tools.collection import ToolCollection
from server.utils.telemetry import capture_ai_generation

from .message_converter import convert_anthropic_to_openai_messages
from .response_converter import convert_openai_to_anthropic_response


class OpenAILegacyChatStrategy:
    """Legacy OpenAI Chat Completions strategy."""

    def __init__(self, handler):
        self.handler = handler

    def prepare_system(self, system_prompt: str) -> str:
        return system_prompt

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[ChatCompletionMessageParam]:
        messages = self.handler.preprocess_messages(messages)
        return convert_anthropic_to_openai_messages(messages)

    def prepare_tools(
        self, tool_collection: ToolCollection
    ) -> list[ChatCompletionToolParam]:
        tools: list[ChatCompletionToolParam] = internal_specs_to_openai_chat_functions(
            list(tool_collection.tools)
        )
        logger.debug(
            'OpenAI legacy tools after conversion: '
            f'{[t.get("function", {}).get("name") for t in tools]}'
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
    ) -> tuple[ChatCompletion, Any, Any]:
        full_messages: list[ChatCompletionMessageParam] = []
        if system:
            sys_msg: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': system,
            }
            full_messages.append(sys_msg)
        full_messages.extend(messages)

        logger.debug(f'Messages: {self.handler._truncate_for_debug(full_messages)}')

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

    def _total_output_tokens(self, parsed_response: Any) -> int:
        return self.handler._total_output_tokens(parsed_response)

    def _capture_generation(
        self,
        parsed_response: Any,
        job_id: str,
        iteration_count: int,
        temperature: float,
        max_tokens: int,
    ) -> None:
        def _get(obj: Any, path: str):
            cur = obj
            for part in path.split('.'):
                if cur is None:
                    return None
                cur = getattr(cur, part, None)
            return cur

        total_output_tokens = self._total_output_tokens(parsed_response)

        capture_ai_generation(
            ai_trace_id=job_id,
            ai_parent_id=str(iteration_count),
            ai_provider='openai',
            ai_model=_get(parsed_response, 'model') or self.handler.model,
            ai_input_tokens=_get(parsed_response, 'usage.prompt_tokens'),
            ai_output_tokens=total_output_tokens,
            ai_cache_read_input_tokens=_get(parsed_response, 'usage.prompt_tokens'),
            ai_cache_creation_input_tokens=_get(
                parsed_response, 'usage.prompt_tokens_details.cached_tokens'
            ),
            ai_temperature=temperature,
            ai_max_tokens=max_tokens,
        )

    async def execute(
        self,
        job_id: str,
        iteration_count: int,
        client: instructor.AsyncInstructor,
        messages: list[BetaMessageParam],
        system: str,
        tools: ToolCollection,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> ProviderExecutionResult:
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

        self._capture_generation(
            parsed_response=parsed_response,
            job_id=job_id,
            iteration_count=iteration_count,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content_blocks, stop_reason = self.convert_from_provider_response(
            parsed_response
        )

        return ProviderExecutionResult(
            content_blocks=content_blocks,
            stop_reason=stop_reason,
            request=request,
            raw_response=raw_response,
        )

    def convert_from_provider_response(
        self, response: ChatCompletion
    ) -> tuple[list[BetaContentBlockParam], str]:
        return convert_openai_to_anthropic_response(response)
