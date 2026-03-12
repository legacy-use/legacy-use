"""Kimi Bedrock provider handler implementation."""

from __future__ import annotations

import json
from typing import Any, Optional

import aioboto3
import httpx
from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam
from botocore.config import Config

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.handlers.opencua.message_converter import (
    extract_api_definitions_from_user_message,
)
from server.computer_use.logging import logger
from server.computer_use.tools.collection import ToolCollection
from server.utils.telemetry import capture_ai_generation

from .message_converter import convert_anthropic_to_kimi_messages
from .response_converter import convert_kimi_to_anthropic_response
from .system_prompt import build_system_prompt


class _LazyBedrockRuntimeClient:
    """Create the Bedrock client only when it is actually entered."""

    def __init__(self, session: aioboto3.Session, config: Config):
        self._session = session
        self._config = config
        self._context = None

    async def __aenter__(self) -> Any:
        self._context = self._session.client(
            service_name='bedrock-runtime',
            config=self._config,
        )
        return await self._context.__aenter__()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._context is None:
            return False
        return await self._context.__aexit__(exc_type, exc, tb)


class KimiBedrockHandler(BaseProviderHandler):
    """Handler for Kimi K2.5 via Amazon Bedrock InvokeModel."""

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
            only_n_most_recent_images=1
            if only_n_most_recent_images is None
            else min(only_n_most_recent_images, 1),
            max_retries=max_retries,
            **kwargs,
        )
        self.model = model
        self._region = 'eu-north-1'
        self.latest_api_definitions: dict[str, str] = {}
        self._computer_options: dict[str, Any] = {}
        self._custom_action_names: list[str] = []

    def _truncate_debug_text(self, value: Any, *, limit: int = 4000) -> str:
        """Keep debug text readable without dropping it to an unhelpful stub."""
        if value is None:
            return ''
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        if len(value) <= limit:
            return value
        return f'{value[:limit]}... <truncated {len(value) - limit} chars>'

    def _summarize_content_blocks(
        self, content_blocks: list[BetaContentBlockParam]
    ) -> list[dict[str, Any]]:
        """Produce a readable debug summary of converted content blocks."""
        summary: list[dict[str, Any]] = []
        for block in content_blocks:
            if not isinstance(block, dict):
                summary.append({'type': type(block).__name__})
                continue

            block_type = str(block.get('type') or '')
            if block_type == 'text':
                summary.append(
                    {
                        'type': 'text',
                        'text': self._truncate_debug_text(block.get('text')),
                    }
                )
                continue

            if block_type == 'tool_use':
                summary.append(
                    {
                        'type': 'tool_use',
                        'name': block.get('name'),
                        'input': block.get('input'),
                    }
                )
                continue

            summary.append(block)
        return summary

    def _normalize_usage(self, response: dict[str, Any]) -> dict[str, Any]:
        """Normalize Kimi/OpenAI-style usage into the shared Anthropic-style shape."""
        usage = dict(response.get('usage') or {})
        prompt_tokens = usage.get('prompt_tokens', usage.get('input_tokens'))
        completion_tokens = usage.get('completion_tokens', usage.get('output_tokens'))
        prompt_tokens_details = usage.get('prompt_tokens_details') or {}
        cached_tokens = prompt_tokens_details.get('cached_tokens')

        if prompt_tokens is not None and 'input_tokens' not in usage:
            usage['input_tokens'] = prompt_tokens
        if completion_tokens is not None and 'output_tokens' not in usage:
            usage['output_tokens'] = completion_tokens
        if cached_tokens is not None and 'cache_read_input_tokens' not in usage:
            usage['cache_read_input_tokens'] = cached_tokens

        return usage

    async def initialize_client(self, api_key: str, **kwargs) -> Any:
        aws_access_key = self.tenant_setting_stripped('AWS_ACCESS_KEY_ID')
        aws_secret_key = self.tenant_setting_stripped('AWS_SECRET_ACCESS_KEY')
        aws_session_token = self.tenant_setting_stripped('AWS_SESSION_TOKEN')
        self._region = self.tenant_setting_stripped('AWS_REGION') or self._region

        if not aws_access_key or not aws_secret_key:
            raise ValueError(
                'AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required '
                'for Kimi Bedrock provider.'
            )

        session = aioboto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            aws_session_token=aws_session_token,
            region_name=self._region,
        )

        return _LazyBedrockRuntimeClient(
            session=session,
            config=Config(
                retries={'max_attempts': self.max_retries},
                read_timeout=180,
                connect_timeout=10,
            ),
        )

    def prepare_system(self, system_prompt: str) -> str:
        return build_system_prompt(
            computer_options=self._computer_options,
            custom_action_names=self._custom_action_names,
        )

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[dict[str, Any]]:
        messages = self.preprocess_messages(messages)
        self.latest_api_definitions = {}

        for message in messages:
            if message.get('role') != 'user':
                continue

            content = message.get('content')
            user_text = ''
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        user_text = str(block.get('text') or '')
                        break

            if not user_text:
                continue

            _, api_name, api_response_example, api_prompt_cleanup = (
                extract_api_definitions_from_user_message(user_text)
            )
            self.latest_api_definitions = {
                'api_name': api_name,
                'api_response_example': api_response_example,
                'api_prompt_cleanup': api_prompt_cleanup,
            }
            break

        return convert_anthropic_to_kimi_messages(messages)

    def prepare_tools(self, tool_collection: ToolCollection) -> list[Any]:
        self._computer_options = {}
        self._custom_action_names = []

        for tool in tool_collection.tools:
            tool_name = getattr(tool, 'name', None)
            if tool_name == 'computer':
                spec = tool.internal_spec()
                self._computer_options = spec.get('options') or {}
            elif tool_name == 'custom_action':
                spec = tool.to_params()
                action_name = (
                    spec.get('input_schema', {})
                    .get('properties', {})
                    .get('action_name', {})
                )
                enum_values = action_name.get('enum') or []
                self._custom_action_names = [
                    str(value) for value in enum_values if value is not None
                ]

        return []

    async def make_ai_request(
        self,
        client: Any,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[Any],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> tuple[dict[str, Any], httpx.Request, httpx.Response]:
        full_messages: list[dict[str, Any]] = []
        if system:
            full_messages.append({'role': 'system', 'content': system})
        full_messages.extend(messages)

        body_payload: dict[str, Any] = {
            'messages': full_messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'stream': False,
        }

        logger.debug(f'Kimi Bedrock payload: {self._truncate_for_debug(body_payload)}')

        response = await client.invoke_model(
            modelId=model,
            contentType='application/json',
            accept='application/json',
            body=json.dumps(body_payload).encode('utf-8'),
        )
        body_bytes = await response['body'].read()
        parsed_response = json.loads(body_bytes.decode('utf-8'))
        normalized_response = dict(parsed_response)
        normalized_response['usage'] = self._normalize_usage(parsed_response)
        logger.debug(
            'Kimi Bedrock raw response: '
            f'{self._truncate_for_debug(normalized_response)}'
        )
        model_content = (
            ((parsed_response.get('choices') or [{}])[0].get('message') or {}).get(
                'content'
            )
            if isinstance(parsed_response, dict)
            else None
        )
        logger.debug(
            f'Kimi Bedrock model content: {self._truncate_debug_text(model_content)}'
        )

        request_payload = self._truncate_for_debug(body_payload)
        request = httpx.Request(
            method='POST',
            url=f'https://bedrock-runtime.{self._region}.amazonaws.com/model/{model}/invoke',
            json=request_payload,
        )
        raw_response = httpx.Response(
            status_code=200,
            json=normalized_response,
            request=request,
        )
        return parsed_response, request, raw_response

    def _capture_generation(
        self,
        response: dict[str, Any],
        job_id: str,
        iteration_count: int,
        temperature: float,
        max_tokens: int,
    ) -> None:
        usage = self._normalize_usage(response)

        def _get(field: str) -> int | None:
            value = usage.get(field)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        capture_ai_generation(
            ai_trace_id=job_id,
            ai_parent_id=str(iteration_count),
            ai_provider='kimi_bedrock',
            ai_model=response.get('model') or self.model,
            ai_input_tokens=_get('prompt_tokens') or _get('input_tokens'),
            ai_output_tokens=_get('completion_tokens') or _get('output_tokens'),
            ai_cache_read_input_tokens=_get('cache_read_input_tokens'),
            ai_temperature=temperature,
            ai_max_tokens=max_tokens,
        )

    def _needs_screenshot(self, messages: list[dict[str, Any]]) -> bool:
        user_messages = [
            message for message in messages if message.get('role') == 'user'
        ]
        if not user_messages:
            return True

        last_user_message = user_messages[-1]
        return not any(
            isinstance(block, dict) and block.get('type') == 'image_url'
            for block in last_user_message.get('content', [])
        )

    def _build_screenshot_retry(
        self, messages: list[BetaMessageParam]
    ) -> BetaContentBlockParam | None:
        retry_count = 0
        screenshot_ids: list[str] = []
        for block in messages:
            if block.get('role') != 'assistant':
                continue
            content = block.get('content')
            if not isinstance(content, list):
                continue
            for content_block in content:
                if (
                    isinstance(content_block, dict)
                    and content_block.get('type') == 'tool_use'
                    and content_block.get('name') == 'computer'
                    and isinstance(content_block.get('input'), dict)
                    and content_block['input'].get('action') == 'screenshot'
                ):
                    screenshot_ids.append(str(content_block.get('id') or ''))

        if screenshot_ids and screenshot_ids[-1].startswith('toolu_retry_screenshot_'):
            retry_count = int(screenshot_ids[-1].split('_')[-1]) + 1

        if retry_count > self.max_retries:
            logger.warning('Max screenshot retries reached for Kimi Bedrock')
            return None

        return {
            'id': f'toolu_retry_screenshot_{retry_count}',
            'type': 'tool_use',
            'name': 'computer',
            'input': {'action': 'screenshot'},
        }

    def _build_noncompliant_terminal(
        self,
        content_blocks: list[BetaContentBlockParam] | None = None,
    ) -> BetaContentBlockParam:
        """Return a terminal failure tool when the model stops emitting actions."""
        reason = (
            'Kimi response did not include a supported tool action after exhausting '
            'screenshot retries.'
        )

        if content_blocks:
            text_blocks = [
                block
                for block in content_blocks
                if isinstance(block, dict) and block.get('type') == 'text'
            ]
            if text_blocks:
                last_text = str(text_blocks[-1].get('text') or '').strip()
                if last_text:
                    reason = f'{reason} Last response: {last_text[:400]}'

        return {
            'id': 'toolu_kimi_noncompliant_terminate',
            'type': 'tool_use',
            'name': 'ui_not_as_expected',
            'input': {'reasoning': reason},
        }

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
        self.prepare_tools(tools)
        system_text = self.prepare_system(system)
        kimi_messages = self.convert_to_provider_messages(messages)

        if self._needs_screenshot(kimi_messages):
            screenshot_tool = self._build_screenshot_retry(messages)
            if screenshot_tool is None:
                terminal_tool = self._build_noncompliant_terminal()
                return [terminal_tool], 'end_turn', None, None
            return [screenshot_tool], 'tool_use', None, None

        async with client as br_client:
            response, request, raw_response = await self.make_ai_request(
                client=br_client,
                messages=kimi_messages,
                system=system_text,
                tools=[],
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
        logger.debug(
            'Kimi converted content blocks: '
            f'{self._summarize_content_blocks(content_blocks)}; stop_reason={stop_reason}'
        )

        if not any(block.get('type') == 'tool_use' for block in content_blocks):
            screenshot_tool = self._build_screenshot_retry(messages)
            if screenshot_tool is None:
                content_blocks.append(self._build_noncompliant_terminal(content_blocks))
                return content_blocks, 'end_turn', request, raw_response
            content_blocks.append(screenshot_tool)
            stop_reason = 'tool_use'

        return content_blocks, stop_reason, request, raw_response

    def convert_from_provider_response(
        self, response: dict[str, Any]
    ) -> tuple[list[BetaContentBlockParam], str]:
        return convert_kimi_to_anthropic_response(
            response,
            latest_api_definitions=self.latest_api_definitions,
            computer_options=self._computer_options,
        )
