import json
import logging
from typing import Any, Iterable

import boto3
import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
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
                elif isinstance(message['content'], list):
                    # drop all tool_result for now, but screenshot
                    content = []
                    for block in message['content']:
                        if block['type'] == 'text':
                            content.append({'type': 'text', 'text': block['text']})
                        elif (
                            block['type'] == 'tool_result'
                            and block['content']['type'] == 'image'
                        ):
                            image_type = block['content']['type']
                            image_media_type = block['content']['media_type']
                            image_data = block['content']['data']
                            # data:image/png;base64,
                            content.append(
                                {
                                    'type': 'image',
                                    'image': f'data:{image_media_type};{image_type},{image_data}',
                                }
                            )
                else:
                    pass

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
    ) -> tuple[Any, Any, Any]:
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

        resp = client.invoke_endpoint(
            EndpointName=self.ENDPOINT,
            ContentType='application/json',
            Accept='application/json',
            Body=json.dumps(payload).encode('utf-8'),
        )

        result = json.loads(resp['Body'].read().decode('utf-8'))
        print('OpenCua result', result)

        return result

    async def execute(
        self, client: Any, messages: list[BetaMessageParam], system: str, **kwargs
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        """Make raw API call to OpenCua and return provider-specific response."""

        logger.debug(
            f'Messages before conversion: {self._truncate_for_debug(messages)}'
        )

        system_formatted = self.prepare_system(system)
        messages_formatted = self.convert_to_provider_messages(messages)

        result = await self.make_ai_request(
            client, messages_formatted, system_formatted
        )
        return result

    def convert_from_provider_response(
        self, response: Any
    ) -> tuple[list[BetaContentBlockParam], str]:
        """Convert OpenCua response to provider-specific response."""
        pass
