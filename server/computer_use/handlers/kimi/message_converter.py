"""Message conversion utilities for Kimi Bedrock."""

from __future__ import annotations

import base64
import json
from typing import Any

from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam

from server.computer_use.logging import logger


def _media_type_to_bedrock_format(media_type: str | None) -> str:
    if not media_type:
        return 'png'
    value = media_type.lower()
    if 'png' in value:
        return 'png'
    if 'jpeg' in value or 'jpg' in value:
        return 'jpeg'
    if 'webp' in value:
        return 'webp'
    return 'png'


def _image_block_from_base64(
    data: str, media_type: str | None
) -> dict[str, Any] | None:
    try:
        image_bytes = base64.b64decode(data)
    except Exception:
        logger.warning('Failed to decode base64 image data for Kimi Bedrock message')
        return None

    return {
        'image': {
            'format': _media_type_to_bedrock_format(media_type),
            'source': {'bytes': image_bytes},
        }
    }


def _tool_result_text(block: BetaContentBlockParam) -> list[dict[str, Any]]:
    text_blocks: list[dict[str, Any]] = []
    if block.get('error'):
        text_blocks.append({'text': f'Tool error: {block["error"]}'})

    for content_item in block.get('content', []) or []:
        if not isinstance(content_item, dict):
            continue
        ctype = content_item.get('type')
        if ctype == 'text':
            text = str(content_item.get('text') or '')
            if text:
                text_blocks.append({'text': text})
            continue
        if ctype == 'image':
            continue
        try:
            text_blocks.append({'text': json.dumps(content_item, ensure_ascii=False)})
        except TypeError:
            text_blocks.append({'text': str(content_item)})

    if not text_blocks and block.get('is_error'):
        text_blocks.append({'text': 'Tool failed without additional details.'})

    return text_blocks


def _convert_content_block(block: BetaContentBlockParam) -> list[dict[str, Any]]:
    content_blocks: list[dict[str, Any]] = []
    block_type = block.get('type')

    if block_type == 'text':
        content_blocks.append({'text': str(block.get('text') or '')})
        return content_blocks

    if block_type == 'image':
        source = block.get('source') or {}
        if source.get('type') == 'base64':
            image_block = _image_block_from_base64(
                str(source.get('data') or ''),
                source.get('media_type'),
            )
            if image_block:
                content_blocks.append(image_block)
        return content_blocks

    if block_type != 'tool_result':
        return content_blocks

    tool_text_blocks = _tool_result_text(block)
    content_blocks.extend(tool_text_blocks)

    for content_item in block.get('content', []) or []:
        if not isinstance(content_item, dict) or content_item.get('type') != 'image':
            continue
        source = content_item.get('source') or {}
        if source.get('type') != 'base64':
            continue
        image_block = _image_block_from_base64(
            str(source.get('data') or ''),
            source.get('media_type'),
        )
        if image_block:
            content_blocks.append(image_block)

    return content_blocks


def convert_anthropic_to_kimi_messages(
    messages: list[BetaMessageParam],
) -> list[dict[str, Any]]:
    """Convert Anthropic-format messages into Bedrock Converse messages."""
    bedrock_messages: list[dict[str, Any]] = []

    for message in messages:
        role = message.get('role')
        content = message.get('content')
        if isinstance(content, str):
            bedrock_messages.append({'role': role, 'content': [{'text': content}]})
            continue

        if not isinstance(content, list):
            continue

        if role == 'assistant':
            content_blocks = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get('type') == 'text':
                    content_blocks.append({'text': str(block.get('text') or '')})
            if content_blocks:
                bedrock_messages.append({'role': role, 'content': content_blocks})
            continue

        content_blocks = []
        for block in content:
            if not isinstance(block, dict):
                continue
            content_blocks.extend(_convert_content_block(block))

        if content_blocks:
            bedrock_messages.append({'role': role, 'content': content_blocks})

    return bedrock_messages
