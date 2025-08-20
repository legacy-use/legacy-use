import json
import logging
import re
from typing import Any, Dict, Iterable, Optional, cast

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
from server.computer_use.handlers.converter_utils import (
    normalize_key_part,
)
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
- If at any point you notice a deviation from the expected GUI, call the `computer.terminate` tool with the status `failure` and the data `{"reasoning": "<TEXT_REASONING_FOR_TERMINATION>"}`

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
      "status": { "type": "string", "enum": [ "success", "failure" ], "description": "The status of the task" },
      "data": { "type": "json", "description": "The required data, relevant for completing the task, in json: ```json\n{...}```; an empty object if no data is required}"
    },
    "required": [ "status", "data" ]
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

    def _extract_api_definitions_from_user_message(
        self, user_message: str
    ) -> tuple[str, str, str, str]:
        """Extract API definitions (prompt, api_name, api_response_example, api_prompt_cleanup) from the full prompt template string."""

        # 1. Extract the original prompt (everything before "IMPORTANT INSTRUCTIONS")
        prompt_match = re.split(
            r'\n\s*IMPORTANT INSTRUCTIONS FOR RETURNING RESULTS:\s*\n',
            user_message,
            maxsplit=1,
        )
        prompt = prompt_match[0].strip() if len(prompt_match) > 1 else ''

        # 2. Extract api_name
        name_match = re.search(r'"name":\s*"([^"]+)"', user_message)
        api_name = name_match.group(1) if name_match else ''

        # 3. Extract api_response_example
        response_match = re.search(
            r'"result":\s*(.+?)\n\s*}\s*```', user_message, re.DOTALL
        )
        api_response_example = response_match.group(1).strip() if response_match else ''

        # 4. Extract prompt_cleanup
        cleanup_match = re.search(
            r"After you've completed the extraction, please perform these steps to return the system to its original state:\s*(.+?)\n?$",
            user_message,
            re.DOTALL,
        )
        api_prompt_cleanup = cleanup_match.group(1).strip() if cleanup_match else '{}'

        return prompt, api_name, api_response_example, api_prompt_cleanup

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[ChatCompletionMessageParam]:
        """Convert messages to provider-specific format."""
        messages = self.preprocess_messages(messages)

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
                            is_image = (
                                len(block['content']) == 1
                                and block['content'][0]['type'] == 'image'
                            )
                            if not is_image:
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

        # add '# Task Instruction:' to the first user text message; This is needed to adhere to the OpenCua fine-tuning format
        user_messages = [msg for msg in result if msg['role'] == 'user']
        if len(user_messages) > 0:
            prompt, api_name, api_response_example, api_prompt_cleanup = (
                self._extract_api_definitions_from_user_message(
                    user_messages[0]['content'][0]['text']
                )
            )
            print(
                'OpenCua user_messages', repr(self._truncate_for_debug(user_messages))
            )
            print('OpenCua prompt', repr(prompt))
            print('OpenCua api_name', repr(api_name))
            print('OpenCua api_response_example', repr(api_response_example))
            print('OpenCua api_prompt_cleanup', repr(api_prompt_cleanup))

            # update the first user text message with the extracted api definitions
            user_messages[0]['content'][0]['text'] = (
                f'# Task Instruction:\n{prompt}\n\nWhen finished call the `computer.terminate` tool with the status `success` and the data `{api_response_example}`'
            )

            self.latest_api_definitions = {
                'prompt': prompt,
                'api_name': api_name,
                'api_response_example': api_response_example,
                'api_prompt_cleanup': api_prompt_cleanup,
            }

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
            'Messages before conversion: %s',
            self._truncate_for_debug(messages),
        )

        system_formatted = self.prepare_system(system)
        messages_formatted = self.convert_to_provider_messages(messages)

        logger.debug(
            'Messages after conversion: %s',
            self._truncate_for_debug(messages_formatted),
        )

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

        result, request, response = await self.make_ai_request(
            client, messages_formatted, system_formatted
        )

        content_blocks, stop_reason = self.convert_from_provider_response(result)

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

            last_screenshot_tool_use_id = last_screenshot_tool_use_ids[-1]
            if (
                len(last_screenshot_tool_use_ids) > 0
                and 'toolu_retry_screenshot_' in last_screenshot_tool_use_id
            ):
                retry_count = int(last_screenshot_tool_use_id.split('_')[-1]) + 1

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

    def _parse_task(self, text: str) -> Dict[str, Optional[str]]:
        # Normalize newlines
        text = text.strip()

        # Step (optional, e.g. '# Step 1:')
        step_match = re.search(r'#\s*Step\s*([^\n:]+):?', text, re.IGNORECASE)
        step = f'{step_match.group(1).strip()}' if step_match else None

        # Thought
        thought_match = re.search(
            r'##\s*Thought:\s*(.*?)(?=##\s*Action:|##\s*Code:|$)',
            text,
            re.DOTALL | re.IGNORECASE,
        )
        thought = thought_match.group(1).strip() if thought_match else None

        # Action
        action_match = re.search(
            r'##\s*Action:\s*(.*?)(?=##\s*Code:|$)', text, re.DOTALL | re.IGNORECASE
        )
        action = action_match.group(1).strip() if action_match else None

        # Code (inside fenced block or after "## Code:")
        code_match = re.search(
            r'##\s*Code:\s*```(?:python|code)?\n?(.*?)```',
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if not code_match:
            # fallback if no fenced block
            code_match = re.search(
                r'##\s*Code:\s*(.*)', text, re.DOTALL | re.IGNORECASE
            )
        code = code_match.group(1).strip() if code_match else None

        return {'step': step, 'thought': thought, 'action': action, 'code': code}

    def _convert_pyautogui_code_to_tool_use(self, code: str) -> BetaToolUseBlockParam:
        """Convert PyAutoGUI code to tool use."""
        print('_convert_pyautogui_code_to_tool_use code:', code)
        # extract command, these are either pyautogui.<command> or computer.<command>
        if 'pyautogui.' in code:
            command = code.split('pyautogui.')[1]
        elif 'computer.' in code:
            command = code.split('computer.')[1]
        else:
            raise ValueError(f'Unknown command: {code}')

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
            key = command.split('key=')[1].split(')')[0].strip('\'"')
            normalized_key = normalize_key_part(key)
            return _construct_tool_use('key', text=normalized_key)
        elif command.startswith('hotkey'):
            # hotkey(['ctrl', 'alt', 'delete'])
            keys: list[str] = command.split('([')[1].split('])')[0].split(',')
            keys = [key.strip().strip('\'"') for key in keys]
            normalized_keys = [normalize_key_part(key) for key in keys]
            print(
                '_convert_pyautogui_code_to_tool_use keys:',
                keys,
                'normalized:',
                normalized_keys,
            )
            return _construct_tool_use('key', text='+'.join(normalized_keys))
        elif command.startswith('wait'):
            # wait(seconds=1)
            seconds = command.split('seconds=')[1].split(')')[0]
            return _construct_tool_use('wait', duration=float(seconds))
        elif command.startswith('terminate'):
            # terminate(status='success', data='{...}'); TODO: handle data and error cases
            status = command.split('status=')[1].split(',')[0].split(')')[0].strip("'")
            if 'data=' in command:
                data = command.split('data=')[1].split(')')[0].strip("'")
            else:
                data = '{}'

            if data:
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning(f'Invalid JSON in data: {data}')

            print('OpenCua terminate status', repr(status))
            print('OpenCua terminate data', repr(data))

            if status == 'success':
                name = ''
                if self.latest_api_definitions:
                    name = self.latest_api_definitions['api_name']

                return {
                    'id': 'toolu_opencua_terminate',
                    'type': 'tool_use',
                    'name': 'extraction',
                    'input': {'data': {'name': name, 'result': data}},
                }
            else:
                # handle if data is not a dict
                if not isinstance(data, dict) or 'reasoning' not in data:
                    data = {'reasoning': data}

                return {
                    'id': 'toolu_opencua_terminate',
                    'type': 'tool_use',
                    'name': 'ui_not_as_expected',
                    'input': {'data': {'reasoning': data['reasoning']}},
                }

        raise ValueError(f'Unknown command: {command}')

    def convert_from_provider_response(
        self, response: str
    ) -> tuple[list[BetaContentBlockParam], str]:
        """Convert OpenCua response to provider-specific response."""

        print('OpenCua response', repr(response))

        task = self._parse_task(response)

        print('OpenCua task', repr(task))

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

                tool_use = self._convert_pyautogui_code_to_tool_use(command)
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

        print('OpenCua messages', repr(messages), 'stop_reason', stop_reason)

        return messages, stop_reason
