"""
Qwen Bedrock message conversion utilities.

Converts Anthropic-style messages into Bedrock Converse format.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Tuple

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


def _image_block_from_base64(data: str, media_type: str | None) -> Dict[str, Any]:
    try:
        image_bytes = base64.b64decode(data)
    except Exception:
        logger.warning('Failed to decode base64 image data for Bedrock message')
        return {}
    return {
        'image': {
            'format': _media_type_to_bedrock_format(media_type),
            'source': {'bytes': image_bytes},
        }
    }


def _extract_tool_result_content(
    block: BetaContentBlockParam,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    status = 'error' if block.get('is_error') or block.get('error') else 'success'
    text_chunks: List[str] = []
    image_blocks: List[Dict[str, Any]] = []

    if block.get('error'):
        text_chunks.append(str(block.get('error') or ''))

    for content_item in block.get('content', []) or []:
        if not isinstance(content_item, dict):
            continue
        ctype = content_item.get('type')
        if ctype == 'text':
            text_chunks.append(str(content_item.get('text') or ''))
        elif ctype == 'image':
            source = content_item.get('source') or {}
            if source.get('type') != 'base64':
                continue
            data = source.get('data')
            if not data:
                continue
            image_block = _image_block_from_base64(data, source.get('media_type'))
            if image_block:
                image_blocks.append(image_block)
        else:
            try:
                text_chunks.append(json.dumps(content_item, ensure_ascii=False))
            except TypeError:
                text_chunks.append(str(content_item))

    if not text_chunks:
        text_chunks.append('Tool executed successfully.')

    tool_content = [{'text': text} for text in text_chunks if text]
    return tool_content, image_blocks, status


def _convert_content_block(
    block: BetaContentBlockParam,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    bedrock_blocks: List[Dict[str, Any]] = []
    extra_blocks: List[Dict[str, Any]] = []

    block_type = block.get('type')
    if block_type == 'text':
        bedrock_blocks.append({'text': str(block.get('text') or '')})
    elif block_type == 'image':
        source = block.get('source') or {}
        if source.get('type') == 'base64':
            data = source.get('data')
            if data:
                image_block = _image_block_from_base64(data, source.get('media_type'))
                if image_block:
                    bedrock_blocks.append(image_block)
    elif block_type == 'tool_use':
        bedrock_blocks.append(
            {
                'toolUse': {
                    'toolUseId': str(block.get('id') or ''),
                    'name': str(block.get('name') or ''),
                    'input': block.get('input') or {},
                }
            }
        )
    elif block_type == 'tool_result':
        tool_content, image_blocks, status = _extract_tool_result_content(block)
        bedrock_blocks.append(
            {
                'toolResult': {
                    'toolUseId': str(block.get('tool_use_id') or ''),
                    'content': tool_content,
                    'status': status,
                }
            }
        )
        # Qwen may reject images in toolResult.content, so keep them separate.
        extra_blocks.extend(image_blocks)

    return bedrock_blocks, extra_blocks


def convert_anthropic_to_bedrock_messages(
    messages: List[BetaMessageParam],
) -> List[Dict[str, Any]]:
    """
    Convert Anthropic-format messages to Bedrock Converse format.
    """
    bedrock_messages: List[Dict[str, Any]] = []

    logger.info(f'Converting {len(messages)} messages from Anthropic to Bedrock format')

    for msg in messages:
        role = msg.get('role')
        content = msg.get('content')

        if isinstance(content, str):
            bedrock_messages.append({'role': role, 'content': [{'text': content}]})
            continue

        if not isinstance(content, list):
            continue

        content_blocks: List[Dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            primary, extras = _convert_content_block(block)
            content_blocks.extend(primary)
            content_blocks.extend(extras)

        if not content_blocks:
            continue

        bedrock_messages.append({'role': role, 'content': content_blocks})

    logger.debug(f'Converted to {len(bedrock_messages)} Bedrock messages')

    return bedrock_messages
