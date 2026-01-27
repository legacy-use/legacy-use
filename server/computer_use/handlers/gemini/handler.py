"""
Gemini provider handler implementation.

Handles Gemini-specific logic and mapping between Gemini and Anthropic formats.
"""

from __future__ import annotations

from typing import Any, List, Optional

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
)
from google import genai
from google.genai import types
from google.genai.types import HttpOptions

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools.base import BaseAnthropicTool
from server.computer_use.tools.collection import ToolCollection
from server.settings import settings
from server.utils.telemetry import capture_ai_generation

from .message_converter import convert_anthropic_to_gemini_messages
from .response_converter import convert_gemini_to_anthropic_response

GEMINI_EXCLUDED_PREDEFINED_FUNCTIONS = [
    'open_web_browser',
    'search',
    'navigate',
    'go_back',
    'go_forward',
]

COMPUTER_ACTIONS_COVERED_BY_GEMINI = {
    'left_click',
    'mouse_move',
    'type',
    'key',
    'scroll',
    'left_click_drag',
}


class GeminiHandler(BaseProviderHandler):
    """Handler for Gemini API provider."""

    def __init__(
        self,
        model: str,
        tenant_schema: str,
        only_n_most_recent_images: Optional[int] = None,
        max_retries: int = 2,
        **kwargs,
    ):
        super().__init__(
            tenant_schema=tenant_schema,
            only_n_most_recent_images=only_n_most_recent_images,
            max_retries=max_retries,
            **kwargs,
        )
        self.model = model
        self._computer_tool: Any | None = None

    async def initialize_client(self, api_key: str, **kwargs) -> Any:
        tenant_key = self.tenant_setting('GOOGLE_GENAI_API_KEY')
        final_api_key = tenant_key or api_key or settings.GOOGLE_GENAI_API_KEY
        if not final_api_key:
            raise ValueError(
                'Gemini API key is required. Please provide either '
                'GOOGLE_GENAI_API_KEY tenant setting or api_key parameter.'
            )
        return genai.Client(
            api_key=final_api_key, http_options=HttpOptions(api_version='v1beta')
        )

    def prepare_system(self, system_prompt: str) -> str:
        return system_prompt

    def _spec_to_function_declaration(
        self, spec: dict[str, Any]
    ) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=str(spec.get('name') or ''),
            description=str(spec.get('description') or ''),
            parameters=spec.get('input_schema')
            or {
                'type': 'object',
                'properties': {},
            },
        )

    def _computer_tool_custom_declarations(
        self, tool: BaseAnthropicTool
    ) -> List[types.FunctionDeclaration]:
        spec = tool.internal_spec()
        actions = spec.get('actions') or []
        declarations: List[types.FunctionDeclaration] = []

        for action in actions:
            action_name = action.get('name')
            if not action_name or action_name in COMPUTER_ACTIONS_COVERED_BY_GEMINI:
                continue
            params = action.get('params') or {}
            required = action.get('required') or []
            description = action.get('description') or f'Computer action: {action_name}'
            declarations.append(
                types.FunctionDeclaration(
                    name=action_name,
                    description=description,
                    parameters={
                        'type': 'object',
                        'properties': params,
                        'required': required,
                    },
                )
            )
        return declarations

    def prepare_tools(self, tool_collection: ToolCollection) -> List[types.Tool]:
        self._computer_tool = next(
            (
                tool
                for tool in tool_collection.tools
                if getattr(tool, 'name', None) == 'computer'
            ),
            None,
        )

        function_declarations: List[types.FunctionDeclaration] = []

        for tool in tool_collection.tools:
            if getattr(tool, 'name', None) == 'computer':
                function_declarations.extend(
                    self._computer_tool_custom_declarations(tool)
                )
                continue
            function_declarations.append(
                self._spec_to_function_declaration(tool.internal_spec())
            )

        tools: List[types.Tool] = [
            types.Tool(
                computer_use=types.ComputerUse(
                    environment=types.Environment.ENVIRONMENT_BROWSER,
                    excluded_predefined_functions=GEMINI_EXCLUDED_PREDEFINED_FUNCTIONS,
                )
            )
        ]

        if function_declarations:
            tools.append(types.Tool(function_declarations=function_declarations))

        logger.debug(
            f'Gemini tools prepared: custom={len(function_declarations)} excluded={GEMINI_EXCLUDED_PREDEFINED_FUNCTIONS}'
        )

        return tools

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[Any]:
        messages = self.preprocess_messages(messages)
        return convert_anthropic_to_gemini_messages(
            messages, computer_tool=self._computer_tool
        )

    async def make_ai_request(
        self,
        client: Any,
        messages: list[Any],
        system: str,
        tools: List[types.Tool],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> tuple[Any, httpx.Request | None, Any]:
        config_kwargs: dict[str, Any] = {}
        if system:
            config_kwargs['system_instruction'] = system
        if tools:
            config_kwargs['tools'] = tools
        if max_tokens:
            config_kwargs['max_output_tokens'] = max_tokens
        if temperature is not None:
            config_kwargs['temperature'] = temperature

        config = types.GenerateContentConfig(**config_kwargs)

        logger.debug(f'Gemini contents: {self._truncate_for_debug(messages)}')

        response = await client.aio.models.generate_content(
            model=model, contents=messages, config=config
        )
        return response, None, response

    def _capture_generation(
        self,
        response: Any,
        job_id: str,
        iteration_count: int,
        temperature: float,
        max_tokens: int,
    ) -> None:
        usage = getattr(response, 'usage_metadata', None) or getattr(
            response, 'usage', None
        )

        def _get(field: str) -> int | None:
            if not usage:
                return None
            if isinstance(usage, dict):
                value = usage.get(field)
            else:
                value = getattr(usage, field, None)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        capture_ai_generation(
            ai_trace_id=job_id,
            ai_parent_id=str(iteration_count),
            ai_provider='gemini',
            ai_model=getattr(response, 'model', None) or self.model,
            ai_input_tokens=_get('prompt_token_count') or _get('prompt_tokens'),
            ai_output_tokens=_get('candidates_token_count')
            or _get('completion_tokens'),
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
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        gemini_tools = self.prepare_tools(tools)
        gemini_messages = self.convert_to_provider_messages(messages)
        system_str = self.prepare_system(system)

        response, request, raw_response = await self.make_ai_request(
            client=client,
            messages=gemini_messages,
            system=system_str,
            tools=gemini_tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        self._capture_generation(
            response=response,
            job_id=job_id,
            iteration_count=iteration_count,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content_blocks, stop_reason = self.convert_from_provider_response(response)

        return content_blocks, stop_reason, request, raw_response  # type: ignore[return-value]

    def convert_from_provider_response(
        self, response: Any
    ) -> tuple[list[BetaContentBlockParam], str]:
        return convert_gemini_to_anthropic_response(
            response, computer_tool=self._computer_tool
        )
