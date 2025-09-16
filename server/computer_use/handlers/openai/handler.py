"""
OpenAI provider handler implementation.

This handler manages all OpenAI-specific logic and mapping between OpenAI's format
and the Anthropic format used for DB storage.
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
from server.computer_use.tools.collection import ToolCollection
from server.utils.telemetry import capture_ai_generation

from .message_converter import convert_anthropic_to_openai_messages
from .response_converter import convert_openai_to_anthropic_response


class OpenAIHandler(BaseProviderHandler):
    """
    Handler for OpenAI API provider.
    """

    def __init__(
        self,
        model: str,
        tenant_schema: str,
        only_n_most_recent_images: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize the OpenAI handler.

        Args:
            model: Model identifier
            token_efficient_tools_beta: Not used for OpenAI
            only_n_most_recent_images: Number of recent images to keep
            **kwargs: Additional provider-specific parameters
        """
        super().__init__(
            tenant_schema=tenant_schema,
            only_n_most_recent_images=only_n_most_recent_images,
            **kwargs,
        )
        self.model = model

    async def initialize_client(
        self, api_key: str, **kwargs
    ) -> instructor.AsyncInstructor:
        """Initialize OpenAI client."""
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
        """
        Prepare system prompt for OpenAI.
        """
        return system_prompt

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[ChatCompletionMessageParam]:
        """
        Convert Anthropic-format messages to OpenAI format.
        """
        # Apply common preprocessing
        messages = self.preprocess_messages(messages)
        return convert_anthropic_to_openai_messages(messages)

    def prepare_tools(
        self, tool_collection: ToolCollection
    ) -> list[ChatCompletionToolParam]:
        """Convert tool collection to OpenAI format."""
        # Build OpenAI tool definitions from each tool's internal_spec().
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
        """Make raw API call to OpenAI and return provider-specific response."""
        # Build full message list with system message
        full_messages: list[ChatCompletionMessageParam] = []
        if system:
            sys_msg: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': system,
            }
            full_messages.append(sys_msg)
        full_messages.extend(messages)

        # Log debug information
        logger.debug(f'Messages: {self._truncate_for_debug(full_messages)}')

        # Make API call
        # Use max_completion_tokens for gpt-5, else max_tokens
        params: dict[str, Any] = dict(
            model=model,
            messages=full_messages,
            tools=tools,
        )
        if model.lower().startswith('gpt-5'):
            params['max_completion_tokens'] = max_tokens
            # gpt-5 doesn't support temperature yet
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
        def _get(obj: Any, path: str):
            cur = obj
            for part in path.split('.'):
                if cur is None:
                    return None
                cur = getattr(cur, part, None)
            return cur

        def _safe_int(value: Any) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        output_tokens_raw = _get(parsed_response, 'usage.completion_tokens')
        reasoning_tokens_raw = _get(
            parsed_response, 'usage.completion_tokens_details.reasoning_tokens'
        )
        return _safe_int(output_tokens_raw) + _safe_int(reasoning_tokens_raw)

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
            ai_model=_get(parsed_response, 'model') or self.model,
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
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        """Make API call to OpenAI and return standardized response format."""
        # Convert inputs to provider format
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

        # Convert response to standardized format
        content_blocks, stop_reason = self.convert_from_provider_response(
            parsed_response
        )

        return content_blocks, stop_reason, request, raw_response

    def convert_from_provider_response(
        self, response: ChatCompletion
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Convert OpenAI response to Anthropic format blocks and stop reason.
        """
        return convert_openai_to_anthropic_response(response)
