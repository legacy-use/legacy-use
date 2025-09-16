"""
Utility functions for Computer Use API Gateway.
"""

import json
from datetime import datetime
from typing import Any, Dict, cast

from anthropic.types.beta import (
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
* DATE: {current_date}

**Core Rules**
1. Always prioritize tool calls over text. Keep text replies short, clear, and concise.
2. First step: take a screenshot. Use only one tool per step.
3. Click button centers; to type Windows key use `Super_L`.
4. After each action, verify the screenshot matches expectations.
   If UI is different or unexpected, stop and call `ui_not_as_expected`.  
   Do not try to fix it yourself unless instructed.
5. If a tool fails, check the error. Retry once; if it still fails after 2 turns, call `ui_not_as_expected`.
6. Always return found information via the extraction tool:
   <extraction>{{"data": {{...}}}}</extraction>
   Never output JSON directly in text.
7. Chain related actions in one tool call when possible to save time.
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

        return cast(
            BetaToolResultBlockParam,
            {
                'type': 'tool_result',
                'tool_use_id': tool_use_id,
                'content': [{'type': 'text', 'text': result.error}],
                'is_error': True,
            },
        )

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

                return cast(
                    BetaToolResultBlockParam,
                    {
                        'type': 'tool_result',
                        'tool_use_id': tool_use_id,
                        'content': [],
                        'error': f'Error: Invalid JSON in extraction tool output: {e}',
                    },
                )
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
) -> list[Dict[str, Any]]:
    """
    Converts a BetaMessageParam TypedDict into components needed for a JobMessage
    (role and serialized message_content). Does not create a JobMessage DB model instance.
    """
    content = beta_param.get('content')
    if isinstance(content, list):
        return cast(list[Dict[str, Any]], content)
    if isinstance(content, str):
        return cast(list[Dict[str, Any]], [{'type': 'text', 'text': content}])
    return []
