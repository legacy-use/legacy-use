"""
Gemini message conversion utilities.

This module contains utilities for converting messages between Gemini and Anthropic formats.
"""

from typing import Any, Optional

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
)

from server.computer_use.logging import logger


def convert_anthropic_to_gemini_messages(
    messages: list[BetaMessageParam],
) -> list[dict[str, Any]]:
    """
    Convert Anthropic-format messages to Gemini format.

    Gemini format:
    {
        "role": "user" | "model",
        "parts": [
            {"text": "..."},
            {"inline_data": {"mime_type": "...", "data": "..."}},
            {"function_call": {"name": "...", "args": {...}}},
            {"function_response": {"name": "...", "response": {...}}}
        ]
    }

    IMPORTANT: Gemini requires alternating user/model roles.
    Tool results must be sent as function_response parts.
    """
    gemini_messages: list[dict[str, Any]] = []

    logger.info(f'Converting {len(messages)} messages from Anthropic to Gemini format')

    msg_idx = 0
    while msg_idx < len(messages):
        msg = messages[msg_idx]
        role = msg['role']
        content = msg['content']

        # Map roles: assistant -> model
        gemini_role = 'model' if role == 'assistant' else 'user'

        logger.debug(
            f'  Message {msg_idx}: role={role} -> {gemini_role}, '
            f'content_type={type(content).__name__}'
        )

        if isinstance(content, str):
            # Simple text message
            gemini_messages.append(
                {
                    'role': gemini_role,
                    'parts': [{'text': content}],
                }
            )
            msg_idx += 1

        elif isinstance(content, list):
            # Check if this message contains tool results
            has_tool_results = any(
                isinstance(block, dict) and block.get('type') == 'tool_result'
                for block in content
            )

            if has_tool_results and role == 'user':
                # Process tool result messages
                tool_response_parts, msg_idx = _process_tool_result_messages(
                    messages, msg_idx
                )
                if tool_response_parts:
                    gemini_messages.append(
                        {
                            'role': 'user',
                            'parts': tool_response_parts,
                        }
                    )
            else:
                # Process regular content blocks
                parts = _convert_content_blocks(content)
                if parts:
                    gemini_messages.append(
                        {
                            'role': gemini_role,
                            'parts': parts,
                        }
                    )
                msg_idx += 1

    logger.debug(f'Converted to {len(gemini_messages)} Gemini messages')
    logger.debug(f'Message roles: {[m["role"] for m in gemini_messages]}')

    return gemini_messages


def _convert_content_blocks(
    content: list[BetaContentBlockParam],
) -> list[dict[str, Any]]:
    """Convert a list of Anthropic content blocks to Gemini parts."""
    parts: list[dict[str, Any]] = []

    for block in content:
        if not isinstance(block, dict):
            continue

        block_type = block.get('type')

        if block_type == 'text':
            text = block.get('text', '')
            if text:
                parts.append({'text': text})

        elif block_type == 'image':
            source = block.get('source', {})
            if source.get('type') == 'base64':
                media_type = source.get('media_type', 'image/png')
                data = source.get('data', '')
                parts.append(
                    {
                        'inline_data': {
                            'mime_type': media_type,
                            'data': data,
                        }
                    }
                )

        elif block_type == 'tool_use':
            # Convert tool use to function call
            parts.append(
                {
                    'function_call': {
                        'name': str(block.get('name') or ''),
                        'args': block.get('input', {}),
                    }
                }
            )

    return parts


def _process_tool_result_block(
    block: BetaContentBlockParam,
) -> tuple[str, dict[str, Any], Optional[dict[str, Any]]]:
    """
    Process a single tool result block.

    Args:
        block: Tool result block from Anthropic format

    Returns:
        Tuple of (tool_use_id, response_content, image_data or None)
    """
    tool_use_id = str(block.get('tool_use_id') or 'tool_call')
    response_content: dict[str, Any] = {}
    image_data: Optional[dict[str, Any]] = None

    if 'error' in block:
        response_content = {'error': str(block['error'])}
    elif 'content' in block and isinstance(block['content'], list):
        for content_item in block['content']:
            if isinstance(content_item, dict):
                if content_item.get('type') == 'text':
                    response_content['output'] = content_item.get('text', '')
                elif content_item.get('type') == 'image':
                    source = content_item.get('source', {})
                    if source.get('type') == 'base64':
                        image_data = {
                            'inline_data': {
                                'mime_type': source.get('media_type', 'image/png'),
                                'data': source.get('data', ''),
                            }
                        }
                        # Also note in response that image was included
                        response_content['has_screenshot'] = True

    if not response_content:
        response_content = {'output': 'Tool executed successfully'}

    return tool_use_id, response_content, image_data


def _process_tool_result_messages(
    messages: list[BetaMessageParam], start_idx: int
) -> tuple[list[dict[str, Any]], int]:
    """
    Process consecutive tool result messages.

    Args:
        messages: List of all messages
        start_idx: Starting index for processing

    Returns:
        Tuple of (Gemini parts list, next index to process)
    """
    parts: list[dict[str, Any]] = []
    accumulated_images: list[dict[str, Any]] = []

    # We need to track tool_use_ids to match function_responses to their calls
    # In Gemini, function_response needs to reference the function name, not an ID
    tool_name_map: dict[str, str] = {}

    # Look back to find the preceding assistant message with tool_use blocks
    # to get the tool names
    if start_idx > 0:
        prev_msg = messages[start_idx - 1]
        if prev_msg['role'] == 'assistant' and isinstance(prev_msg['content'], list):
            for block in prev_msg['content']:
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    tool_id = str(block.get('id') or '')
                    tool_name = str(block.get('name') or '')
                    if tool_id and tool_name:
                        tool_name_map[tool_id] = tool_name

    current_idx = start_idx
    while current_idx < len(messages):
        current_msg = messages[current_idx]
        current_role = current_msg['role']
        current_content = current_msg['content']

        # Only process user messages with tool_result blocks
        if current_role != 'user' or not isinstance(current_content, list):
            break

        has_tool_result = False
        for block in current_content:
            if isinstance(block, dict) and block.get('type') == 'tool_result':
                has_tool_result = True
                tool_use_id, response_content, image_data = _process_tool_result_block(
                    block
                )

                # Get the tool name from our map, or use the ID as fallback
                tool_name = tool_name_map.get(tool_use_id, tool_use_id)

                # Create function_response part
                parts.append(
                    {
                        'function_response': {
                            'name': tool_name,
                            'response': response_content,
                        }
                    }
                )

                # Accumulate image if present
                if image_data:
                    accumulated_images.append(image_data)

        if not has_tool_result:
            break
        current_idx += 1

    # Add accumulated images as additional parts
    # Gemini allows multiple parts in a message
    parts.extend(accumulated_images)

    return parts, current_idx


def create_gemini_user_message(content: str) -> dict[str, Any]:
    """Create a simple user message in Gemini format."""
    return {
        'role': 'user',
        'parts': [{'text': content}],
    }


def create_gemini_image_message(
    images: list[tuple[str, str, str]],
) -> dict[str, Any]:
    """
    Create a user message with images.

    Args:
        images: List of (text, base64_data, mime_type) tuples

    Returns:
        Gemini user message with image content
    """
    parts: list[dict[str, Any]] = []

    for text, img_data, mime_type in images:
        if text:
            parts.append({'text': text})
        parts.append(
            {
                'inline_data': {
                    'mime_type': mime_type,
                    'data': img_data,
                }
            }
        )

    return {
        'role': 'user',
        'parts': parts,
    }
