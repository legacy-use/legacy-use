"""Message conversion utilities for OpenAI handler."""

import json
from typing import Optional, cast

from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)

from server.computer_use.logging import logger


def create_text_message(role: str, content: str) -> ChatCompletionMessageParam:
    """Create a simple text message in OpenAI format."""
    if role == 'user':
        return {
            'role': 'user',
            'content': content,
        }
    else:
        return {
            'role': 'assistant',
            'content': content,
        }


def process_tool_result_block(
    block: BetaContentBlockParam,
) -> tuple[str, str, Optional[str]]:
    """Process a single tool result block."""
    tool_call_id = block.get('tool_use_id')
    text_content = ''
    image_data = None

    if 'error' in block:
        text_content = str(block['error'])
    elif 'content' in block and isinstance(block['content'], list):
        for content_item in block['content']:
            if isinstance(content_item, dict):
                if content_item.get('type') == 'text':
                    text_content = content_item.get('text', '')
                elif content_item.get('type') == 'image':
                    source = content_item.get('source', {})
                    if source.get('type') == 'base64':
                        image_data = str(source.get('data'))

    return str(tool_call_id or 'tool_call'), text_content, image_data


def create_tool_message(
    tool_call_id: str, content: str
) -> ChatCompletionToolMessageParam:
    """Create a tool message in OpenAI format."""
    return {
        'role': 'tool',
        'tool_call_id': tool_call_id,
        'content': str(content or 'Tool executed successfully'),
    }


def create_image_message(
    images: list[tuple[str, str]],
) -> ChatCompletionUserMessageParam:
    """Create a user message with images."""
    user_parts: list[ChatCompletionContentPartParam] = []

    for text, img_data in images:
        if text:
            user_parts.append({'type': 'text', 'text': text})
        user_parts.append(
            {
                'type': 'image_url',
                'image_url': {'url': f'data:image/png;base64,{img_data}'},
            }
        )

    return {
        'role': 'user',
        'content': user_parts,
    }


def convert_content_block(
    block: BetaContentBlockParam,
) -> tuple[
    Optional[ChatCompletionContentPartParam],
    Optional[ChatCompletionMessageToolCallParam],
]:
    """Convert a single content block to OpenAI format."""
    block_type = block.get('type')

    if block_type == 'text':
        content_part = cast(
            ChatCompletionContentPartTextParam,
            {
                'type': 'text',
                'text': block.get('text', ''),
            },
        )
        return content_part, None

    elif block_type == 'image':
        source = block.get('source', {})
        if source.get('type') == 'base64':
            content_part = cast(
                ChatCompletionContentPartImageParam,
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:{source.get("media_type", "image/png")};base64,{source.get("data", "")}',
                    },
                },
            )
            return content_part, None

    elif block_type == 'tool_use':
        tool_call = cast(
            ChatCompletionMessageToolCallParam,
            {
                'id': str(block.get('id') or ''),
                'type': 'function',
                'function': {
                    'name': str(block.get('name') or ''),
                    'arguments': json.dumps(block.get('input', {})),
                },
            },
        )
        return None, tool_call

    return None, None


def process_tool_result_messages(
    messages: list[BetaMessageParam], start_idx: int
) -> tuple[list[ChatCompletionMessageParam], int]:
    """Process consecutive tool result messages."""
    tool_messages: list[ChatCompletionToolMessageParam] = []
    accumulated_images: list[tuple[str, str]] = []

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
                tool_call_id, text_content, image_data = process_tool_result_block(
                    block
                )

                tool_messages.append(create_tool_message(tool_call_id, text_content))

                if image_data:
                    accumulated_images.append((text_content, str(image_data)))

        if not has_tool_result:
            break
        current_idx += 1

    result_messages: list[ChatCompletionMessageParam] = []
    result_messages.extend(tool_messages)

    if accumulated_images:
        result_messages.append(create_image_message(accumulated_images))

    return result_messages, current_idx


def convert_to_openai_messages(
    messages: list[BetaMessageParam],
) -> list[ChatCompletionMessageParam]:
    """Convert Anthropic-format messages to OpenAI format."""
    openai_messages: list[ChatCompletionMessageParam] = []

    logger.info(f'Converting {len(messages)} messages from Anthropic to OpenAI format')

    msg_idx = 0
    while msg_idx < len(messages):
        msg = messages[msg_idx]
        role = msg['role']
        content = msg['content']

        logger.debug(
            f'  Message {msg_idx}: role={role}, content_type={type(content).__name__}'
        )

        if isinstance(content, str):
            openai_messages.append(create_text_message(role, content))
            msg_idx += 1

        elif isinstance(content, list):
            has_tool_results = any(
                isinstance(block, dict) and block.get('type') == 'tool_result'
                for block in content
            )

            if has_tool_results and role == 'user':
                tool_messages, msg_idx = process_tool_result_messages(messages, msg_idx)
                openai_messages.extend(tool_messages)
            else:
                content_parts: list[ChatCompletionContentPartParam] = []
                tool_calls: list[ChatCompletionMessageToolCallParam] = []

                for block in content:
                    if isinstance(block, dict):
                        content_part, tool_call = convert_content_block(block)
                        if content_part:
                            content_parts.append(content_part)
                        if tool_call:
                            tool_calls.append(tool_call)

                if role == 'user' and content_parts:
                    openai_messages.append(
                        {
                            'role': 'user',
                            'content': content_parts,
                        }
                    )
                elif role == 'assistant':
                    assistant_msg: ChatCompletionAssistantMessageParam = {
                        'role': 'assistant',
                    }

                    if content_parts:
                        texts = [
                            str(part.get('text') or '')
                            for part in content_parts
                            if isinstance(part, dict) and part.get('type') == 'text'
                        ]
                        if texts:
                            assistant_msg['content'] = '\n'.join(t for t in texts if t)

                    if tool_calls:
                        assistant_msg['tool_calls'] = tool_calls

                    openai_messages.append(assistant_msg)

                msg_idx += 1

    logger.debug(f'Converted to {len(openai_messages)} OpenAI messages')
    logger.debug(f'Message types: {[m["role"] for m in openai_messages]}')

    return openai_messages
