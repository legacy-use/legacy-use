"""
Utility functions for Computer Use API Gateway.
"""

import json
from datetime import datetime
from typing import Any, Dict, cast

from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.logging import logger
from server.computer_use.tools import ToolResult


def _load_system_prompt(system_prompt_suffix: str = '') -> str:
    """
    Load and format the system prompt with current values.

    Args:
        system_prompt_suffix: Optional additional text to append to the system prompt
    """
    # Define the system prompt directly in the code
    system_prompt = """<SYSTEM_CAPABILITY>
* IMPORTANT BEHAVIOUR: If you want to click a button, make sure you click it right in the center of the button. If you want to type the Windows key, use Super_L instead.
* IMPORTANT UI CHECKING: After most computer function calls, you receive a screenshot back. Do verify that the screenshot is what you expected.
* If the UI doesn't match your expectations or looks different, use the ui_not_as_expected tool to report it with a clear explanation. The user has written the prompt with an UI in mind and the UI might be different.
* If that is hte case, call the ui_not_as_expected tool to ask the user how to proceed <ui_not_as_expected tool>{{'reason':'...'}}</ui_not_as_expected tool>. Do not proceed if the UI is different from what the prompt let's you expect.
* Be especially careful when you are asked to enter text, that the field you enter has focus. If the field does not have focus, call ui_not_as_expected with the reason that the field does not have focus.
* DO NOT PROCEED IF THE UI IS DIFFERENT FROM WHAT THE PROMPT LETS YOU EXPECT. DO NOT TRY TO RECTIFY IT YOURSELF. IF IN DOUBT, ASK THE USER HOW TO PROCEED VIA THE ui_not_as_expected tool.
* IMPORTANT EXTRACTION: When you've found the information requested by the user, ALWAYS use the extraction tool to return the result as structured JSON data. NEVER output JSON directly in text.
* The extraction tool should be used like this: <extraction tool>{{"name": "API_NAME", "result": {{...}}}}</extraction tool>
* When using your computer function calls, they take a while to run and send back to you. Where possible/feasible, try to chain multiple of these calls all into one function calls request.
* The current date is {current_date}.
* IMPORTANT PRIORITY: Always priotize a tool call over a text response. To send an extraction back to the user, always use the extraction tool, do not respond in a JSON format in the message.
</SYSTEM_CAPABILITY>"""

    # Format the prompt with current values
    formatted_prompt = system_prompt.format(
        current_date=datetime.today().strftime('%A, %B %-d, %Y')
    )

    # Append suffix if provided
    if system_prompt_suffix:
        formatted_prompt = f'{formatted_prompt} {system_prompt_suffix}'

    return formatted_prompt


def _response_to_params(
    response: BetaMessage,
) -> list[BetaContentBlockParam]:
    res: list[BetaContentBlockParam] = []
    for block in response.content:
        if isinstance(block, BetaTextBlock):
            if block.text:
                res.append(BetaTextBlockParam(type='text', text=block.text))
            elif getattr(block, 'type', None) == 'thinking':
                # Handle thinking blocks - include signature field
                thinking_block = {
                    'type': 'thinking',
                    'thinking': getattr(block, 'thinking', None),
                }
                if hasattr(block, 'signature'):
                    thinking_block['signature'] = getattr(block, 'signature', None)
                res.append(cast(BetaContentBlockParam, thinking_block))
        else:
            # Handle tool use blocks normally
            res.append(cast(BetaToolUseBlockParam, block.model_dump()))
    return res


def _inject_prompt_caching(
    messages: list[BetaMessageParam],
):
    """
    Set cache breakpoints for the 3 most recent turns
    one cache breakpoint is left for tools/system prompt, to be shared across sessions
    """

    breakpoints_remaining = 3
    for message in reversed(messages):
        if message['role'] == 'user' and isinstance(
            content := message['content'], list
        ):
            if breakpoints_remaining:
                breakpoints_remaining -= 1
                content[-1]['cache_control'] = BetaCacheControlEphemeralParam(
                    {'type': 'ephemeral'}
                )
            else:
                content[-1].pop('cache_control', None)
                # we'll only every have one extra turn per loop
                break


def _maybe_filter_to_n_most_recent_images(
    messages: list[BetaMessageParam],
    images_to_keep: int,
    min_removal_threshold: int,
):
    """
    With the assumption that images are screenshots that are of diminishing value as
    the conversation progresses, remove all but the final `images_to_keep` tool_result
    images in place, with a chunk of min_removal_threshold to reduce the amount we
    break the implicit prompt cache.
    """
    if images_to_keep is None:
        return messages

    tool_result_blocks = cast(
        list[BetaToolResultBlockParam],
        [
            item
            for message in messages
            for item in (
                message['content'] if isinstance(message['content'], list) else []
            )
            if isinstance(item, dict) and item.get('type') == 'tool_result'
        ],
    )

    total_images = sum(
        1
        for tool_result in tool_result_blocks
        for content in tool_result.get('content', [])
        if isinstance(content, dict) and content.get('type') == 'image'
    )

    images_to_remove = total_images - images_to_keep
    # for better cache behavior, we want to remove in chunks
    images_to_remove -= images_to_remove % min_removal_threshold

    for tool_result in tool_result_blocks:
        if isinstance(tool_result.get('content'), list):
            new_content = []
            for content in tool_result.get('content', []):
                if isinstance(content, dict) and content.get('type') == 'image':
                    if images_to_remove > 0:
                        images_to_remove -= 1
                        continue
                new_content.append(content)
            tool_result['content'] = new_content


def _make_api_tool_result(
    result: ToolResult, tool_use_id: str
) -> BetaToolResultBlockParam:
    """Convert an agent ToolResult to an API ToolResultBlockParam."""
    # Check if this is an extraction tool result
    is_extraction = 'extraction' in tool_use_id

    if result.error:
        # For error case, return the error in the expected format
        return {
            'type': 'tool_result',
            'tool_use_id': tool_use_id,
            'content': [],
            'error': _maybe_prepend_system_tool_result(result, result.error),
        }

    # For success case, prepare the content
    content: list[BetaTextBlockParam | BetaImageBlockParam] = []

    if result.output:
        # Special handling for extraction tool results
        if is_extraction:
            logger.info(f'Processing extraction tool output: {result.output}')
            # Ensure proper JSON formatting for extraction results
            try:
                # Parse and validate the JSON
                json_data = json.loads(result.output)
                logger.info(f'Valid JSON extraction data: {json_data}')

                # Extract just the result field from the extraction data
                if isinstance(json_data, dict) and 'result' in json_data:
                    result_data = json_data['result']
                    # Return the formatted JSON as text
                    formatted_output = json.dumps(
                        result_data, indent=2, ensure_ascii=False
                    )
                    content.append(
                        {
                            'type': 'text',
                            'text': _maybe_prepend_system_tool_result(
                                result, formatted_output
                            ),
                        }
                    )
                else:
                    # If no result field, return the whole data
                    formatted_output = json.dumps(
                        json_data, indent=2, ensure_ascii=False
                    )
                    content.append(
                        {
                            'type': 'text',
                            'text': _maybe_prepend_system_tool_result(
                                result, formatted_output
                            ),
                        }
                    )
            except json.JSONDecodeError as e:
                logger.error(f'Invalid JSON in extraction tool output: {e}')
                # Return error message when JSON is invalid
                return {
                    'type': 'tool_result',
                    'tool_use_id': tool_use_id,
                    'content': [],
                    'error': f'Error: Invalid JSON in extraction tool output: {e}',
                }
        else:
            # Standard handling for non-extraction tools
            content.append(
                {
                    'type': 'text',
                    'text': _maybe_prepend_system_tool_result(result, result.output),
                }
            )

    if result.base64_image:
        content.append(
            {
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': 'image/png',
                    'data': result.base64_image,
                },
            }
        )

    # If there's no content, add a default message
    if not content:
        content.append({'type': 'text', 'text': 'system: Tool returned no output.'})

    # Return the properly formatted tool result for success case
    return {'type': 'tool_result', 'tool_use_id': tool_use_id, 'content': content}


def _maybe_prepend_system_tool_result(result: ToolResult, result_text: str):
    if result.system:
        result_text = f'<system>{result.system}</system>\n{result_text}'
    return result_text


def _job_message_to_beta_message_param(job_message: Dict[str, Any]) -> BetaMessageParam:
    """Converts a JobMessage dictionary (or model instance) to a BetaMessageParam TypedDict."""
    # Deserialize from JSON to plain dict
    restored = {
        'role': job_message.get('role'),
        'content': job_message.get('message_content'),
    }
    # Optional: cast for type checkers (runtime it's still just a dict)
    restored = cast(BetaMessageParam, restored)

    return restored


def _beta_message_param_to_job_message_content(
    beta_param: BetaMessageParam,
) -> Dict[str, Any]:
    """
    Converts a BetaMessageParam TypedDict into components needed for a JobMessage
    (role and serialized message_content). Does not create a JobMessage DB model instance.
    """
    return beta_param.get('content')


# OpenAI Conversion Functions


def _anthropic_to_openai_messages(
    anthropic_messages: list[BetaMessageParam],
) -> list[Dict[str, Any]]:
    """Convert Anthropic messages to OpenAI format."""
    openai_messages = []

    for msg in anthropic_messages:
        role = msg.get('role')
        content = msg.get('content')

        if role == 'assistant':
            # Handle assistant messages with potential tool calls
            openai_msg = {'role': 'assistant'}
            text_content = ''
            tool_calls = []

            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get('type') == 'text':
                            text_content += block.get('text', '')
                        elif block.get('type') == 'tool_use':
                            tool_calls.append(
                                {
                                    'id': block.get('id'),
                                    'type': 'function',
                                    'function': {
                                        'name': block.get('name'),
                                        'arguments': json.dumps(block.get('input', {})),
                                    },
                                }
                            )

            if text_content:
                openai_msg['content'] = text_content
            if tool_calls:
                openai_msg['tool_calls'] = tool_calls

            openai_messages.append(openai_msg)

        elif role == 'user':
            # Handle user messages with potential tool results
            openai_msg = {'role': 'user'}
            text_content = ''

            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get('type') == 'text':
                            text_content += block.get('text', '')
                        elif block.get('type') == 'image':
                            # Handle image content
                            image_data = block.get('source', {})
                            if image_data.get('type') == 'base64':
                                text_content += (
                                    f'[Image: {image_data.get("media_type", "image")}]'
                                )
                        elif block.get('type') == 'tool_result':
                            # Convert tool result to tool message
                            tool_msg = {
                                'role': 'tool',
                                'tool_call_id': block.get('tool_use_id'),
                                'content': '',
                            }

                            # Extract content from tool result
                            tool_content = block.get('content', [])
                            if isinstance(tool_content, list):
                                for tc in tool_content:
                                    if (
                                        isinstance(tc, dict)
                                        and tc.get('type') == 'text'
                                    ):
                                        tool_msg['content'] += tc.get('text', '')
                                    elif (
                                        isinstance(tc, dict)
                                        and tc.get('type') == 'image'
                                    ):
                                        # For tool results with images, include base64 data
                                        image_data = tc.get('source', {})
                                        if image_data.get('type') == 'base64':
                                            tool_msg['content'] += (
                                                f'\n[Image: data:{image_data.get("media_type", "image/png")};base64,{image_data.get("data", "")}]'
                                            )

                            if block.get('error'):
                                tool_msg['content'] += f'\nError: {block.get("error")}'

                            openai_messages.append(tool_msg)

            if text_content.strip():
                openai_msg['content'] = text_content
                openai_messages.append(openai_msg)

    return openai_messages


def _openai_to_anthropic_messages(
    openai_messages: list[Dict[str, Any]],
) -> list[BetaMessageParam]:
    """Convert OpenAI messages to Anthropic format."""
    anthropic_messages = []

    for msg in openai_messages:
        role = msg.get('role')

        if role == 'assistant':
            content = []

            # Add text content if present
            if msg.get('content'):
                content.append({'type': 'text', 'text': msg['content']})

            # Add tool calls if present
            if msg.get('tool_calls'):
                for tool_call in msg['tool_calls']:
                    if tool_call.get('type') == 'function':
                        func = tool_call.get('function', {})
                        content.append(
                            {
                                'type': 'tool_use',
                                'id': tool_call.get('id'),
                                'name': func.get('name'),
                                'input': json.loads(func.get('arguments', '{}')),
                            }
                        )

            anthropic_messages.append({'role': 'assistant', 'content': content})

        elif role == 'user':
            content = []

            if msg.get('content'):
                content.append({'type': 'text', 'text': msg['content']})

            anthropic_messages.append({'role': 'user', 'content': content})

        elif role == 'tool':
            # Convert tool message to tool_result in user message
            tool_result = {
                'type': 'tool_result',
                'tool_use_id': msg.get('tool_call_id'),
                'content': [],
            }

            content_text = msg.get('content', '')
            if content_text:
                # Check if content contains base64 image data
                if '[Image: data:' in content_text:
                    # Extract text and image parts
                    parts = content_text.split('[Image: data:')
                    if parts[0].strip():
                        tool_result['content'].append(
                            {'type': 'text', 'text': parts[0].strip()}
                        )

                    # Handle image data
                    for part in parts[1:]:
                        if ';base64,' in part:
                            media_type, rest = part.split(';base64,', 1)
                            if ']' in rest:
                                base64_data, remaining_text = rest.split(']', 1)
                                tool_result['content'].append(
                                    {
                                        'type': 'image',
                                        'source': {
                                            'type': 'base64',
                                            'media_type': media_type,
                                            'data': base64_data,
                                        },
                                    }
                                )
                                if remaining_text.strip():
                                    tool_result['content'].append(
                                        {'type': 'text', 'text': remaining_text.strip()}
                                    )
                else:
                    tool_result['content'].append(
                        {'type': 'text', 'text': content_text}
                    )

            # Add to last user message or create new one
            if anthropic_messages and anthropic_messages[-1]['role'] == 'user':
                anthropic_messages[-1]['content'].append(tool_result)
            else:
                anthropic_messages.append({'role': 'user', 'content': [tool_result]})

    return anthropic_messages


def _openai_response_to_anthropic_params(
    openai_response: Dict[str, Any],
) -> list[BetaContentBlockParam]:
    """Convert OpenAI response to Anthropic content blocks."""
    content_blocks = []

    message = openai_response.get('choices', [{}])[0].get('message', {})

    # Add text content
    if message.get('content'):
        content_blocks.append({'type': 'text', 'text': message['content']})

    # Add tool calls
    if message.get('tool_calls'):
        for tool_call in message['tool_calls']:
            if tool_call.get('type') == 'function':
                func = tool_call.get('function', {})
                content_blocks.append(
                    {
                        'type': 'tool_use',
                        'id': tool_call.get('id'),
                        'name': func.get('name'),
                        'input': json.loads(func.get('arguments', '{}')),
                    }
                )

    return content_blocks
