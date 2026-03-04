"""Message conversion utilities for Kimi Bedrock native invocation."""

from __future__ import annotations

import json
from typing import Any

from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam


def _tool_result_text(block: BetaContentBlockParam) -> list[dict[str, Any]]:
    text_blocks: list[dict[str, Any]] = []
    if block.get('error'):
        text_blocks.append({'type': 'text', 'text': f'Tool error: {block["error"]}'})

    for content_item in block.get('content', []) or []:
        if not isinstance(content_item, dict):
            continue
        ctype = content_item.get('type')
        if ctype == 'text':
            text = str(content_item.get('text') or '')
            if text:
                text_blocks.append({'type': 'text', 'text': text})
            continue
        if ctype == 'image':
            continue
        try:
            text_blocks.append(
                {'type': 'text', 'text': json.dumps(content_item, ensure_ascii=False)}
            )
        except TypeError:
            text_blocks.append({'type': 'text', 'text': str(content_item)})

    if not text_blocks and block.get('is_error'):
        text_blocks.append(
            {'type': 'text', 'text': 'Tool failed without additional details.'}
        )

    return text_blocks


def _convert_content_block(block: BetaContentBlockParam) -> list[dict[str, Any]]:
    content_blocks: list[dict[str, Any]] = []
    block_type = block.get('type')

    if block_type == 'text':
        content_blocks.append({'type': 'text', 'text': str(block.get('text') or '')})
        return content_blocks

    if block_type == 'image':
        source = block.get('source') or {}
        if source.get('type') == 'base64':
            media_type = source.get('media_type') or 'image/png'
            data = str(source.get('data') or '')
            if data:
                content_blocks.append(
                    {
                        'type': 'image_url',
                        'image_url': {'url': f'data:{media_type};base64,{data}'},
                    }
                )
        return content_blocks

    if block_type != 'tool_result':
        return content_blocks

    content_blocks.extend(_tool_result_text(block))

    for content_item in block.get('content', []) or []:
        if not isinstance(content_item, dict) or content_item.get('type') != 'image':
            continue
        source = content_item.get('source') or {}
        if source.get('type') != 'base64':
            continue
        media_type = source.get('media_type') or 'image/png'
        data = str(source.get('data') or '')
        if data:
            content_blocks.append(
                {
                    'type': 'image_url',
                    'image_url': {'url': f'data:{media_type};base64,{data}'},
                }
            )

    return content_blocks


def convert_anthropic_to_kimi_messages(
    messages: list[BetaMessageParam],
) -> list[dict[str, Any]]:
    """Convert Anthropic-format messages into Kimi native chat messages."""
    kimi_messages: list[dict[str, Any]] = []

    for message in messages:
        role = message.get('role')
        content = message.get('content')
        if isinstance(content, str):
            kimi_messages.append(
                {'role': role, 'content': [{'type': 'text', 'text': content}]}
            )
            continue

        if not isinstance(content, list):
            continue

        if role == 'assistant':
            content_blocks = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get('type') == 'text':
                    content_blocks.append(
                        {'type': 'text', 'text': str(block.get('text') or '')}
                    )
            if content_blocks:
                kimi_messages.append({'role': role, 'content': content_blocks})
            continue

        content_blocks = []
        for block in content:
            if not isinstance(block, dict):
                continue
            content_blocks.extend(_convert_content_block(block))

        if content_blocks:
            kimi_messages.append({'role': role, 'content': content_blocks})

    return kimi_messages
