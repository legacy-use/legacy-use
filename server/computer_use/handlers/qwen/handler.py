"""
Qwen Bedrock provider handler implementation.

Uses Bedrock Converse with Qwen3-VL via the Anthropic-style sampling loop.
"""

from __future__ import annotations

from typing import Any, Optional

import aioboto3
import httpx
from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam
from botocore.config import Config

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools.base import BaseAnthropicTool
from server.computer_use.tools.collection import ToolCollection
from server.utils.telemetry import capture_ai_generation

from .message_converter import convert_anthropic_to_bedrock_messages
from .response_converter import convert_bedrock_to_anthropic_response


class QwenBedrockHandler(BaseProviderHandler):
    """Handler for Qwen3-VL via Amazon Bedrock Converse."""

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
        self._forced_region = 'eu-west-2'

    async def initialize_client(self, api_key: str, **kwargs) -> Any:
        aws_access_key = self.tenant_setting_stripped('AWS_ACCESS_KEY_ID')
        aws_secret_key = self.tenant_setting_stripped('AWS_SECRET_ACCESS_KEY')
        aws_session_token = self.tenant_setting_stripped('AWS_SESSION_TOKEN')

        if not aws_access_key or not aws_secret_key:
            raise ValueError(
                'AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required '
                'for Qwen Bedrock provider.'
            )

        session = aioboto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            aws_session_token=aws_session_token,
            region_name=self._forced_region,
        )

        client = session.client(
            service_name='bedrock-runtime',
            config=Config(
                retries={'max_attempts': self.max_retries},
                read_timeout=180,
                connect_timeout=10,
            ),
        )
        return client

    def prepare_system(self, system_prompt: str) -> list[dict[str, str]]:
        return [{'text': system_prompt}]

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[dict[str, Any]]:
        messages = self.preprocess_messages(messages)
        return convert_anthropic_to_bedrock_messages(messages)

    def _spec_to_bedrock_tool(self, spec: dict[str, Any]) -> dict[str, Any]:
        name = str(spec.get('name') or '')
        description = str(spec.get('description') or f'Tool: {name}')
        parameters = spec.get('input_schema') or {'type': 'object', 'properties': {}}
        return {
            'toolSpec': {
                'name': name,
                'description': description,
                'inputSchema': {'json': parameters},
            }
        }

    def _expand_computer_tools(self, tool: BaseAnthropicTool) -> list[dict[str, Any]]:
        spec = tool.internal_spec()
        actions = spec.get('actions') or []
        tools: list[dict[str, Any]] = []

        for action in actions:
            action_name = str(action.get('name') or '')
            params = action.get('params') or {}
            required = action.get('required') or []
            description = action.get('description') or f'Computer action: {action_name}'
            tools.append(
                {
                    'toolSpec': {
                        'name': action_name,
                        'description': description,
                        'inputSchema': {
                            'json': {
                                'type': 'object',
                                'properties': params,
                                'required': required,
                            }
                        },
                    }
                }
            )
        return tools

    def prepare_tools(self, tool_collection: ToolCollection) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for tool in tool_collection.tools:
            if getattr(tool, 'name', None) == 'computer':
                tools.extend(self._expand_computer_tools(tool))
            else:
                tools.append(self._spec_to_bedrock_tool(tool.internal_spec()))

        logger.debug(
            'Qwen Bedrock tools prepared: '
            f'{[t.get("toolSpec", {}).get("name") for t in tools]}'
        )
        return tools

    async def make_ai_request(
        self,
        client: Any,
        messages: list[dict[str, Any]],
        system: list[dict[str, str]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> tuple[dict[str, Any], httpx.Request, httpx.Response]:
        payload: dict[str, Any] = {
            'modelId': model,
            'messages': messages,
            'inferenceConfig': {
                'maxTokens': max_tokens,
                'temperature': temperature,
            },
        }
        if system:
            payload['system'] = system
        if tools:
            payload['toolConfig'] = {'tools': tools}

        logger.debug(f'Bedrock Converse payload: {self._truncate_for_debug(payload)}')

        response = await client.converse(**payload)

        def _sanitize(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            if isinstance(obj, (bytes, bytearray)):
                return '<binary data>'
            return obj

        request_payload = _sanitize(payload)
        request = httpx.Request(
            method='POST',
            url=f'https://bedrock-runtime.{self._forced_region}.amazonaws.com/model/{model}/converse',
            json=request_payload,
        )
        raw_response = httpx.Response(
            status_code=200,
            json=response,
            request=request,
        )
        return response, request, raw_response

    def _capture_generation(
        self,
        response: dict[str, Any],
        job_id: str,
        iteration_count: int,
        temperature: float,
        max_tokens: int,
    ) -> None:
        usage = response.get('usage') or {}

        def _get(field: str) -> int | None:
            value = usage.get(field)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        capture_ai_generation(
            ai_trace_id=job_id,
            ai_parent_id=str(iteration_count),
            ai_provider='qwen_bedrock',
            ai_model=response.get('modelId') or self.model,
            ai_input_tokens=_get('inputTokens') or _get('promptTokens'),
            ai_output_tokens=_get('outputTokens') or _get('completionTokens'),
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
        bedrock_messages = self.convert_to_provider_messages(messages)
        system_blocks = self.prepare_system(system)
        bedrock_tools = self.prepare_tools(tools)

        async with client as br_client:
            response, request, raw_response = await self.make_ai_request(
                client=br_client,
                messages=bedrock_messages,
                system=system_blocks,
                tools=bedrock_tools,
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

        return content_blocks, stop_reason, request, raw_response

    def convert_from_provider_response(
        self, response: dict[str, Any]
    ) -> tuple[list[BetaContentBlockParam], str]:
        return convert_bedrock_to_anthropic_response(response)
