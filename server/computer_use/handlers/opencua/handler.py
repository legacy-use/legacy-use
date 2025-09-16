"""Main OpenCUA handler implementation."""

import json
import logging
from typing import Any, Dict, Iterable, cast

import aioboto3
import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)
from botocore.config import Config

from server.computer_use.config import APIProvider
from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.tools.collection import ToolCollection
from server.utils.telemetry import capture_ai_generation

from .message_converter import convert_to_opencua_messages_and_extract_api_definitions
from .pyautogui_converter import convert_pyautogui_code_to_tool_use, parse_task
from .system_prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class OpenCuaHandler(BaseProviderHandler):
    """Handler for OpenCUA API provider."""

    def __init__(
        self,
        provider: APIProvider,
        model: str,
        tenant_schema: str,
        max_retries: int = 2,
        **kwargs,
    ):
        only_n_most_recent_images = 1  # to save on vram
        super().__init__(
            tenant_schema=tenant_schema,
            only_n_most_recent_images=only_n_most_recent_images,
            max_retries=max_retries,
        )

        self.provider = provider
        self.model = model
        self.endpoint = model
        self.latest_api_definitions: Dict[str, str] = {}

    async def initialize_client(self, api_key: str, **kwargs):
        """Initialize OpenCua client."""
        # AWS credentials from tenant settings

        aws_region = self.tenant_setting('AWS_REGION')
        aws_access_key = self.tenant_setting('AWS_ACCESS_KEY_ID')
        aws_secret_key = self.tenant_setting('AWS_SECRET_ACCESS_KEY')

        # Create session with explicit credentials
        session = aioboto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )

        client = session.client(
            service_name='sagemaker-runtime',
            config=Config(
                retries={
                    'max_attempts': self.max_retries,
                },
                read_timeout=180,
            ),
        )

        return client

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[Any]:
        """Convert messages to provider-specific format."""

        messages = self.preprocess_messages(messages)

        converted_messages, latest_api_definitions = (
            convert_to_opencua_messages_and_extract_api_definitions(messages)
        )
        self.latest_api_definitions = latest_api_definitions

        return converted_messages

    def prepare_system(self, system_prompt: str) -> str:
        """Prepare system prompt for OpenCua."""
        # Overwrite system prompt for now. Our current system prompt breaks the model.
        return SYSTEM_PROMPT

    def prepare_tools(self, tool_collection: ToolCollection) -> list[str]:
        """Prepare tools for OpenCua."""
        # Tools must be manually added to the opencua specific system prompt.
        # Simply adding them to the system prompt will break the model,
        # so one needs to "engineer" new tools into the available tools,
        # already specified in the system prompt.
        return []

    async def make_ai_request(
        self, client: Any, messages: list[Any], system: Iterable[Any]
    ) -> tuple[str, Any, Any]:
        """Make raw API call to OpenCua and return provider-specific response."""

        full_messages = []
        if system:
            full_messages.append({'role': 'system', 'content': system})
        full_messages.extend(messages)

        logger.debug(f'Messages: {self._truncate_for_debug(full_messages)}')

        payload = {'messages': full_messages}

        response = await client.invoke_endpoint(
            EndpointName=self.endpoint,
            ContentType='application/json',
            Accept='application/json',
            Body=json.dumps(payload).encode('utf-8'),
        )
        body_bytes = await response['Body'].read()
        result = json.loads(body_bytes.decode('utf-8'))['text']

        return result, None, response

    async def execute(
        self,
        job_id: str,
        iteration_count: int,
        client: Any,
        messages: list[BetaMessageParam],
        system: str,
        **kwargs,
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        """Make raw API call to OpenCua and return provider-specific response."""

        system_formatted = self.prepare_system(system)
        messages_formatted = self.convert_to_provider_messages(messages)

        # if the last user messages does not include a screenshot (image), add one
        last_user_message = [
            msg for msg in messages_formatted if msg['role'] == 'user'
        ][-1]
        if not any(block['type'] == 'image' for block in last_user_message['content']):
            logger.info(
                'No screenshot found in last user message, adding mock screenshot tool use'
            )
            # return tool_use with screenshot
            mock_screenshot_tool_use: BetaToolUseBlockParam = {
                'id': 'toolu_retry_screenshot_0',
                'type': 'tool_use',
                'name': 'computer',
                'input': {'action': 'screenshot'},
            }
            return [mock_screenshot_tool_use], 'tool_use', None, None

        async with client as sm_client:
            result, request, response = await self.make_ai_request(
                sm_client, messages_formatted, system_formatted
            )

        content_blocks, stop_reason = self.convert_from_provider_response(result)

        capture_ai_generation(
            ai_trace_id=job_id,
            ai_parent_id=str(iteration_count),
            ai_provider=self.provider,
            ai_model=self.model,
            # More meaningful metrics are not yet supported by our SageMaker endpoint
        )

        # if the last block is not a tool_use, add a mock screenshot tool use
        if len(content_blocks) == 0 or content_blocks[-1]['type'] != 'tool_use':
            logger.info('Last block is not a tool_use, adding mock screenshot tool use')
            retry_count = 0
            # Collect all tool_use blocks with screenshot action for retry id calculation
            last_screenshot_tool_use_ids = []
            for block in messages:
                if block.get('role') != 'assistant':
                    continue
                content = block.get('content')
                if not isinstance(content, list):
                    continue
                for content_block in content:
                    if (
                        content_block.get('type') == 'tool_use'
                        and content_block.get('name') == 'computer'
                        and isinstance(content_block.get('input'), dict)
                        and content_block['input'].get('action') == 'screenshot'
                    ):
                        last_screenshot_tool_use_ids.append(content_block['id'])

            if (
                len(last_screenshot_tool_use_ids) > 0
                and 'toolu_retry_screenshot_' in last_screenshot_tool_use_ids[-1]
            ):
                retry_count = int(last_screenshot_tool_use_ids[-1].split('_')[-1]) + 1

            if retry_count > self.max_retries:
                logger.warning('Max retries reached, terminating task')
                return [], 'end_turn', request, response

            mock_screenshot_tool_use: BetaToolUseBlockParam = {
                'id': f'toolu_retry_screenshot_{retry_count}',
                'type': 'tool_use',
                'name': 'computer',
                'input': {'action': 'screenshot'},
            }
            content_blocks.append(mock_screenshot_tool_use)

        return content_blocks, stop_reason, request, response

    def convert_from_provider_response(
        self, response: str
    ) -> tuple[list[BetaContentBlockParam], str]:
        """Convert OpenCua response to provider-specific response."""

        task = parse_task(response)

        messages: list[BetaContentBlockParam] = []
        stop_reason = 'end_turn'

        # construct text message from task
        text_message = ''
        if task['step']:
            text_message += f'# Step: {task["step"]}\n'
        if task['action']:
            text_message += f'## Action: {task["action"]}\n'

        if text_message:
            messages.append(
                cast(BetaTextBlockParam, {'type': 'text', 'text': text_message})
            )

        if task['code']:
            commands = task['code'].split('\n')
            for command in commands:
                command = command.strip()
                if not command:
                    continue

                tool_use = convert_pyautogui_code_to_tool_use(
                    command, self.latest_api_definitions
                )
                messages.append(tool_use)

                # End the turn once extraction or ui_not_as_expected is called
                if tool_use['id'] == 'toolu_opencua_terminate':
                    # potentially overwrite stop_reason with end_turn
                    stop_reason = 'end_turn'
                    break

                stop_reason = 'tool_use'

        # thought can be dropped, as it's is more or less just unstructured reasoning output of the model itself
        # the paper does not include it in the message history for L2 reasoning (which has the best performance)
        # can be interesting for the user to be debug, but one needs to be aware that it's reasoning output as the quality of the text is quite low

        return messages, stop_reason
