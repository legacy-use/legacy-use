"""OpenAI provider facade with legacy Chat and GA Responses strategies."""

from __future__ import annotations

from typing import Any, Optional

import instructor
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
)
from openai import AsyncOpenAI

from server.computer_use.handlers.base import (
    BaseProviderHandler,
    ProviderExecutionResult,
)
from server.computer_use.tools.collection import ToolCollection

from .legacy_chat_handler import OpenAILegacyChatStrategy
from .responses_handler import OpenAIResponsesComputerStrategy

OPENAI_RESPONSES_COMPUTER_PREFIXES = ('gpt-5.4',)


class OpenAIHandler(BaseProviderHandler):
    """Facade that routes OpenAI models to the correct execution strategy."""

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
        self._legacy_strategy = OpenAILegacyChatStrategy(self)
        self._responses_strategy = OpenAIResponsesComputerStrategy(self)

    def _uses_responses_computer(self, model: str | None = None) -> bool:
        model_name = (model or self.model or '').lower()
        return model_name.startswith(OPENAI_RESPONSES_COMPUTER_PREFIXES)

    def _strategy(self, model: str | None = None):
        if self._uses_responses_computer(model):
            return self._responses_strategy
        return self._legacy_strategy

    async def initialize_client(self, api_key: str, **kwargs) -> Any:
        tenant_key = self.tenant_setting('OPENAI_API_KEY')
        final_api_key = tenant_key or api_key
        if not final_api_key:
            raise ValueError(
                'OpenAI API key is required. Please provide either '
                'OPENAI_API_KEY tenant setting or api_key parameter.'
            )

        openai_client = AsyncOpenAI(api_key=final_api_key)
        if self._uses_responses_computer():
            return openai_client
        return instructor.from_openai(openai_client, max_retries=self.max_retries)

    def prepare_system(self, system_prompt: str) -> Any:
        return self._strategy().prepare_system(system_prompt)

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[Any]:
        return self._strategy().convert_to_provider_messages(messages)

    def prepare_tools(self, tool_collection: ToolCollection) -> Any:
        return self._strategy().prepare_tools(tool_collection)

    async def make_ai_request(
        self,
        client: Any,
        messages: list[Any],
        system: str,
        tools: Any,
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> Any:
        return await self._strategy(model).make_ai_request(
            client=client,
            messages=messages,
            system=system,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
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
        return await self._strategy(model).execute(
            job_id=job_id,
            iteration_count=iteration_count,
            client=client,
            messages=messages,
            system=system,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def convert_from_provider_response(
        self, response: Any
    ) -> tuple[list[BetaContentBlockParam], str]:
        return self._strategy().convert_from_provider_response(response)
