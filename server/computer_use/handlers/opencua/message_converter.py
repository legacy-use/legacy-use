"""Message conversion utilities for OpenCUA handler."""

import logging
import re
from typing import Dict

from anthropic.types.beta import BetaMessageParam
from openai.types.chat import ChatCompletionMessageParam

logger = logging.getLogger(__name__)


def extract_api_definitions_from_user_message(
    user_message: str,
) -> tuple[str, str, str, str]:
    """Extract API definitions (prompt, api_name, api_response_example, api_prompt_cleanup) from the full prompt template string."""

    # 1. Extract the original prompt (everything before "IMPORTANT INSTRUCTIONS")
    prompt_match = re.split(
        r'\n\s*IMPORTANT INSTRUCTIONS FOR RETURNING RESULTS:\s*\n',
        user_message,
        maxsplit=1,
    )
    prompt = prompt_match[0].strip() if len(prompt_match) > 1 else user_message.strip()

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


def convert_to_opencua_messages(
    messages: list[BetaMessageParam],
) -> tuple[list[ChatCompletionMessageParam], Dict[str, str]]:
    """Convert messages to OpenCua format."""
    result = []
    for message in messages:
        if message['role'] == 'user':
            content = None
            if isinstance(message['content'], str):
                content = [{'type': 'text', 'text': message['content']}]
            elif isinstance(message['content'], list) and len(message['content']) > 0:
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

    api_definitions = {}
    # add '# Task Instruction:' to the first user text message; This is needed to adhere to the OpenCua fine-tuning format
    user_messages = [msg for msg in result if msg['role'] == 'user']
    if len(user_messages) > 0:
        if not (
            len(user_messages[0]['content']) > 0
            and user_messages[0]['content'][0]['type'] == 'text'
        ):
            raise ValueError('First user message must be a text message')
        prompt, api_name, api_response_example, api_prompt_cleanup = (
            extract_api_definitions_from_user_message(
                user_messages[0]['content'][0]['text']
            )
        )

        # update the first user text message with the extracted api definitions
        user_messages[0]['content'][0]['text'] = (
            f'# Task Instruction:\n{prompt}\n\nWhen finished call the `computer.terminate` tool with the status `success` and the data `{api_response_example}`'
        )

        api_definitions = {
            'prompt': prompt,
            'api_name': api_name,
            'api_response_example': api_response_example,
            'api_prompt_cleanup': api_prompt_cleanup,
        }

    return result, api_definitions
