"""Native OpenAI Responses computer-use strategy for gpt-5.4."""

from __future__ import annotations

from typing import Any

from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam

from server.computer_use.handlers.base import ProviderExecutionResult
from server.computer_use.handlers.utils.converter_utils import (
    internal_specs_to_openai_responses_tools,
)
from server.computer_use.logging import logger
from server.computer_use.tools.collection import ToolCollection
from server.utils.telemetry import capture_ai_generation

from .responses_message_converter import build_openai_responses_request
from .responses_response_converter import (
    convert_openai_responses_to_anthropic_response,
)
from .responses_system_prompt import build_openai_responses_system_prompt


class OpenAIResponsesComputerStrategy:
    """OpenAI Responses strategy for native GA computer use."""

    def __init__(self, handler):
        self.handler = handler

    def prepare_system(self, system_prompt: str) -> str:
        return build_openai_responses_system_prompt(system_prompt)

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[BetaMessageParam]:
        return self.handler.preprocess_messages(messages)

    def prepare_tools(self, tool_collection: ToolCollection) -> list[dict[str, Any]]:
        return internal_specs_to_openai_responses_tools(list(tool_collection.tools))

    async def make_ai_request(
        self,
        client: Any,
        messages: list[BetaMessageParam],
        system: str,
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> tuple[Any, Any, Any, dict[str, Any]]:
        request_state = build_openai_responses_request(
            messages=messages,
            provider_state=self.handler.extra_params.get('provider_state'),
        )

        params: dict[str, Any] = {
            'model': model,
            'input': request_state.input_items,
            'tools': tools,
            'max_output_tokens': max_tokens,
            'instructions': system,
        }
        if request_state.previous_response_id:
            params['previous_response_id'] = request_state.previous_response_id

        logger.debug(
            f'OpenAI Responses payload: {self.handler._truncate_for_debug(params)}'
        )

        response = await client.responses.with_raw_response.create(**params)
        parsed_response = response.parse()
        return (
            parsed_response,
            response.http_response.request,
            response.http_response,
            request_state.provider_state,
        )

    def _safe_get(self, obj: Any, *path: str) -> Any:
        cur = obj
        for key in path:
            if cur is None:
                return None
            if isinstance(cur, dict):
                cur = cur.get(key)
            else:
                cur = getattr(cur, key, None)
        return cur

    def _capture_generation(
        self,
        parsed_response: Any,
        job_id: str,
        iteration_count: int,
        temperature: float,
        max_tokens: int,
    ) -> None:
        output_tokens = self._safe_get(parsed_response, 'usage', 'output_tokens')
        reasoning_tokens = self._safe_get(
            parsed_response, 'usage', 'output_tokens_details', 'reasoning_tokens'
        )

        try:
            total_output_tokens = int(output_tokens or 0) + int(reasoning_tokens or 0)
        except (TypeError, ValueError):
            total_output_tokens = 0

        capture_ai_generation(
            ai_trace_id=job_id,
            ai_parent_id=str(iteration_count),
            ai_provider='openai',
            ai_model=self._safe_get(parsed_response, 'model') or self.handler.model,
            ai_input_tokens=self._safe_get(parsed_response, 'usage', 'input_tokens'),
            ai_output_tokens=total_output_tokens,
            ai_temperature=temperature,
            ai_max_tokens=max_tokens,
        )

    async def execute(
        self,
        job_id: str,
        iteration_count: int,
        client: Any,
        messages: list[BetaMessageParam],
        system: str,
        tools: ToolCollection,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> ProviderExecutionResult:
        provider_messages = self.convert_to_provider_messages(messages)
        provider_tools = self.prepare_tools(tools)
        system_prompt = self.prepare_system(system)

        (
            parsed_response,
            request,
            raw_response,
            provider_state,
        ) = await self.make_ai_request(
            client=client,
            messages=provider_messages,
            system=system_prompt,
            tools=provider_tools,
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

        content_blocks, stop_reason, response_provider_state = (
            convert_openai_responses_to_anthropic_response(parsed_response)
        )
        provider_state.update(response_provider_state)

        return ProviderExecutionResult(
            content_blocks=content_blocks,
            stop_reason=stop_reason,
            request=request,
            raw_response=raw_response,
            provider_state=provider_state,
        )

    def convert_from_provider_response(
        self, response: Any
    ) -> tuple[list[BetaContentBlockParam], str]:
        content_blocks, stop_reason, _ = convert_openai_responses_to_anthropic_response(
            response
        )
        return content_blocks, stop_reason
