import json
import logging
from typing import Any, Iterable, cast

import boto3
import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)
from botocore.config import Config
from openai.types.chat import ChatCompletionMessageParam

from server.computer_use.config import APIProvider
from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.tools.collection import ToolCollection

logger = logging.getLogger(__name__)


class OpenCuaHandler(BaseProviderHandler):
    SYSTEM_PROMPT = """You are a GUI agent. You are given a task and a screenshot of the screen.
You need to perform a series of pyautogui actions to complete the task.

For each step, provide your response in this format:

Thought:
- Step by Step Progress Assessment:
  - Analyze completed task parts and their contribution to the overall goal
  - Reflect on potential errors, unexpected results, or obstacles
  - If previous action was incorrect, predict a logical recovery step

- Next Action Analysis:
  - List possible next actions based on current state
  - Evaluate options considering current state and previous actions
  - Propose most logical next action
  - Anticipate consequences of the proposed action

- For Text Input Actions:
  - Note current cursor position
  - Consolidate repetitive actions (specify count for multiple keypresses)
  - Describe expected final text outcome
  - Use first-person perspective in reasoning

Action:
Provide clear, concise, and actionable instructions:
- If the action involves interacting with a specific target:
  - Describe target explicitly without using coordinates
  - Specify element names when possible (use original language if non-English)
  - Describe features (shape, color, position) if name unavailable
- For window control buttons, identify correctly (minimize, maximize, close)
- If the action involves keyboard actions like `press`, `write`, `hotkey`:
  - Consolidate repetitive keypresses with count
  - Specify expected text outcome for typing actions

Finally, output the action as PyAutoGUI code or the following functions:

- {
  "name": "computer.triple_click",
  "description": "Triple click on the screen",
  "parameters": {
    "type": "object",
    "properties": {
      "x": { "type": "number", "description": "The x coordinate of the triple click" },
      "y": { "type": "number", "description": "The y coordinate of the triple click" }
    },
    "required": [ "x", "y" ]
  }
}

- {
  "name": "computer.terminate",
  "description": "Terminate the current task and report its completion status",
  "parameters": {
    "type": "object",
    "properties": {
      "status": { "type": "string", "enum": [ "success", "failure" ], "description": "The status of the task" }
    },
    "required": [ "status" ]
  }
}
"""

    # TODO move to tenant

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
        self.ENDPOINT = self.tenant_setting(
            'AWS_SAGEMAKER_ENDPOINT'
        )  # TODO: endpoint effectively the same as model

    async def initialize_client(self, api_key: str, **kwargs):
        """Initialize OpenCua client."""
        # AWS credentials from tenant settings (fallback to env settings)

        aws_region = self.tenant_setting('AWS_REGION')
        aws_access_key = self.tenant_setting('AWS_ACCESS_KEY_ID')
        aws_secret_key = self.tenant_setting('AWS_SECRET_ACCESS_KEY')

        logger.info(f'Using boto3 session with region: {aws_region}')

        # Create session with explicit credentials (None values will use default credential chain)
        session = boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )

        client = session.client(
            service_name='sagemaker-runtime',
            region_name=aws_region,
            config=Config(
                retries={
                    'max_attempts': self.max_retries,
                }
            ),
        )

        return client

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[ChatCompletionMessageParam]:
        """Convert messages to provider-specific format."""
        result = []
        for message in messages:
            if message['role'] == 'user':
                content = None
                if isinstance(message['content'], str):
                    content = [{'type': 'text', 'text': message['content']}]
                elif (
                    isinstance(message['content'], list) and len(message['content']) > 0
                ):
                    # drop all tool_result for now, but screenshot
                    content = []
                    for block in message['content']:
                        if block['type'] == 'text':
                            content.append({'type': 'text', 'text': block['text']})
                        elif block['type'] == 'tool_result':
                            is_error = 'error' in block and block['error'] is not None
                            if is_error:
                                logger.warning(f'Tool result error: {block["error"]}')

                                continue
                            is_image = block['content'][0]['type'] == 'image'
                            if not is_image:
                                logger.warning(
                                    f'Tool result is not an image: {block["content"]}'
                                )
                                continue
                            block_content = block['content'][0]
                            image_type = block_content['source']['type']
                            image_media_type = block_content['source']['media_type']
                            image_data = block_content['source']['data']
                            # data:image/png;base64,
                            content.append(
                                {
                                    'type': 'image',
                                    'image': f'data:{image_media_type};{image_type},{image_data}',
                                }
                            )
                else:
                    logger.warning(
                        f'Unknown message content type: {type(message["content"])}'
                    )
                    pass

                if content and len(content) > 0:
                    result.append({'role': 'user', 'content': content})
            elif message['role'] == 'assistant':
                # drop all tool_use from assistant messages
                content = None
                if isinstance(message['content'], str):
                    content = [{'type': 'text', 'text': message['content']}]
                elif isinstance(message['content'], list):
                    content = []
                    for block in message['content']:
                        if block['type'] == 'text':
                            content.append({'type': 'text', 'text': block['text']})

                if content and len(content) > 0:
                    result.append({'role': 'assistant', 'content': content})

        return result

    def prepare_system(self, system_prompt: str) -> str:
        """Prepare system prompt for OpenCua."""
        # Overwrite system prompt for now, TODO: think of a good way to include the overarching system prompt
        return self.SYSTEM_PROMPT

    def prepare_tools(self, tool_collection: ToolCollection) -> list[str]:
        """Prepare tools for OpenCua."""
        # Skip for now: TODO: think of a good way to include tools as a json, just like in the system prompt, but without the model breaking
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

        payload = {
            'messages': full_messages,
        }

        # TODO: double check temprature

        response = client.invoke_endpoint(
            EndpointName=self.ENDPOINT,
            ContentType='application/json',
            Accept='application/json',
            Body=json.dumps(payload).encode('utf-8'),
        )

        result = json.loads(response['Body'].read().decode('utf-8'))['text']

        return result, None, response

    async def execute(
        self, client: Any, messages: list[BetaMessageParam], system: str, **kwargs
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        """Make raw API call to OpenCua and return provider-specific response."""

        logger.debug(
            f'Messages before conversion: {self._truncate_for_debug(messages)}'
        )

        system_formatted = self.prepare_system(system)
        messages_formatted = self.convert_to_provider_messages(messages)

        logger.debug(
            'Messages after conversion', self._truncate_for_debug(messages_formatted)
        )

        # if the last user messages does not include a screenshot (image), add one
        # return tool_use with screenshot
        last_user_message = [
            msg for msg in messages_formatted if msg['role'] == 'user'
        ][-1]
        logger.debug('last_user_message', self._truncate_for_debug(last_user_message))
        if not any(block['type'] == 'image' for block in last_user_message['content']):
            logger.info(
                'No screenshot found in last user message, adding mock screenshot tool use'
            )
            mock_screenshot_tool_use: BetaToolUseBlockParam = {
                'id': 'toolu_mock123',
                'type': 'tool_use',
                'name': 'computer',
                'input': {'action': 'screenshot'},
            }
            return [mock_screenshot_tool_use], 'tool_use', None, None

        result, request, response = await self.make_ai_request(
            client, messages_formatted, system_formatted
        )

        content_blocks, stop_reason = self.convert_from_provider_response(result)

        return content_blocks, stop_reason, request, response

    def _extract_assistant_sections(self, response: str) -> tuple[str, str, str, str]:
        """Extract sections from assistant response, supporting multi-line content and flexible section headers."""
        import re

        # Patterns for section headers
        section_patterns = {
            'Step': re.compile(r'^# Step(?:\s*\d*)?:\s*$'),
            'Thought': re.compile(r'^## Thought:\s*$'),
            'Action': re.compile(r'^## Action:\s*$'),
            'Code': re.compile(r'^## Code:\s*$'),
        }

        sections = {'Step': [], 'Thought': [], 'Action': [], 'Code': []}
        current_section = None

        lines = response.splitlines()
        for line in lines:
            matched = False
            for section, pattern in section_patterns.items():
                if pattern.match(line):
                    current_section = section
                    matched = True
                    break
            if not matched and current_section:
                # For code, stop at triple backticks or end of section
                if current_section == 'Code':
                    if line.strip().startswith('```'):
                        continue  # skip the code block marker
                sections[current_section].append(line)

        # Join lines, strip leading/trailing whitespace
        step = '\n'.join(sections['Step']).strip()
        thought = '\n'.join(sections['Thought']).strip()
        action = '\n'.join(sections['Action']).strip()
        code = '\n'.join(sections['Code']).strip()

        return step, thought, action, code

    def _convert_pyautogui_code_to_tool_use(self, code: str) -> BetaToolUseBlockParam:
        """Convert PyAutoGUI code to tool use."""
        print('_convert_pyautogui_code_to_tool_use code:', code)
        command = code.split('pyautogui.')[1]
        print('_convert_pyautogui_code_to_tool_use command:', command)

        def _convert_coordinate(coordinate: str) -> tuple[int, int]:
            """Convert coordinate string to tuple of ints."""
            x = int(coordinate.split('x=')[1].split(',')[0])
            y = int(coordinate.split('y=')[1].split(')')[0])
            return x, y

        def _construct_tool_use(action: str, **args: Any) -> BetaToolUseBlockParam:
            """Construct tool use."""
            return {
                'id': f'toolu_opencua_{action}',
                'type': 'tool_use',
                'name': 'computer',
                'input': {'action': action, **args},
            }

        if command.startswith('click'):
            # click(x=248, y=730)
            x, y = _convert_coordinate(command)
            return _construct_tool_use('left_click', coordinate=[x, y])
        elif command.startswith('rightClick'):
            # rightClick(x=248, y=730)
            x, y = _convert_coordinate(command)
            return _construct_tool_use('right_click', coordinate=[x, y])
        elif command.startswith('middleClick'):
            # middleClick(x=248, y=730)
            x, y = _convert_coordinate(command)
            return _construct_tool_use('middle_click', coordinate=[x, y])
        elif command.startswith('doubleClick'):
            # doubleClick(x=248, y=730)
            x, y = _convert_coordinate(command)
            return _construct_tool_use('double_click', coordinate=[x, y])
        elif command.startswith('tripleClick'):
            # tripleClick(x=248, y=730)
            x, y = _convert_coordinate(command)
            return _construct_tool_use('triple_click', coordinate=[x, y])
        elif command.startswith('moveTo'):
            # moveTo(x=248, y=730)
            x, y = _convert_coordinate(command)
            return _construct_tool_use('mouse_move', coordinate=[x, y])
        elif command.startswith('dragTo'):
            # dragTo(x=248, y=730)
            x, y = _convert_coordinate(command)
            return _construct_tool_use('left_click_drag', coordinate=[x, y])
        elif command.startswith('scroll'):
            # vertical scroll; TODO test
            return _construct_tool_use(
                'scroll', scroll_direction='down', scroll_amount=100
            )
        elif command.startswith('hscroll'):
            # horizontal scroll; TODO test
            return _construct_tool_use(
                'scroll', scroll_direction='right', scroll_amount=100
            )
        elif command.startswith('write'):
            # write(message='Hello, world!'); TODO: make sure ) in the text can be handelt
            text = command.split('message=')[1].split(')')[0]
            return _construct_tool_use('type', text=text)
        elif command.startswith('press'):
            # press('esc')
            key = command.split('key=')[1].split(')')[0]
            return _construct_tool_use('type', text=key)
        elif command.startswith('hotkey'):
            # hotkey(['ctrl', 'alt', 'delete'])
            keys: list[str] = command.split('([')[1].split('])')[0].split(',')
            keys = [key.strip() for key in keys]
            print('_convert_pyautogui_code_to_tool_use keys:', keys)
            return _construct_tool_use('key', text='+'.join(keys))
        elif command.startswith('wait'):
            # wait(seconds=1)
            seconds = command.split('seconds=')[1].split(')')[0]
            return _construct_tool_use('wait', duration=float(seconds))
        elif command.startswith('terminate'):
            # terminate(status='success'); TODO: handle data and error cases
            return {
                'id': 'toolu_opencua_terminate',
                'type': 'tool_use',
                'name': 'extraction',
                'input': {'data': {'name': 'terminate', 'status': 'success'}},
            }

        raise ValueError(f'Unknown command: {command}')

    def convert_from_provider_response(
        self, response: str
    ) -> tuple[list[BetaContentBlockParam], str]:
        """Convert OpenCua response to provider-specific response."""

        step, thought, action, code = self._extract_assistant_sections(response)

        print('OpenCua response', response)
        print('OpenCua step', step)
        print('OpenCua thought', thought)
        print('OpenCua action', action)
        print('OpenCua code', code)

        messages: list[BetaContentBlockParam] = []
        stop_reason = 'end_turn'

        # Only keep the step and action (alligns with samples from the openCua paper);
        # TODO: Having the though displayed in the UI is nice, but hurts model performance
        # -> include and filter out in convert_to_provider_messages
        text_message = f'# Step: {step}\n ## Thought: {thought}\n## Action: {action}'
        messages.append(
            cast(BetaTextBlockParam, {'type': 'text', 'text': text_message})
        )

        if code:
            tool_use = self._convert_pyautogui_code_to_tool_use(code)
            messages.append(tool_use)
            stop_reason = 'tool_use'

        # thought can be dropped, as it's is more or less just reasoning output of the model itself
        # The paper does not include it in the message history, but for the user it might be of interest

        return messages, stop_reason
