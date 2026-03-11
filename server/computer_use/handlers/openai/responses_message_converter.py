"""Build OpenAI Responses API input from Anthropic-style history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anthropic.types.beta import BetaMessageParam

from server.computer_use.logging import logger

OPENAI_COMPUTER_TOOL_USE_PREFIX = 'openai_computer'
OPENAI_FUNCTION_TOOL_USE_PREFIX = 'openai_function'


@dataclass(kw_only=True)
class OpenAIResponsesRequest:
    input_items: list[dict[str, Any]]
    previous_response_id: str | None
    provider_state: dict[str, Any]


def make_openai_computer_tool_use_id(call_id: str, index: int) -> str:
    return f'{OPENAI_COMPUTER_TOOL_USE_PREFIX}:{call_id}:{index}'


def make_openai_function_tool_use_id(call_id: str) -> str:
    return f'{OPENAI_FUNCTION_TOOL_USE_PREFIX}:{call_id}'


def parse_openai_tool_use_id(tool_use_id: str) -> tuple[str, str]:
    if tool_use_id.startswith(f'{OPENAI_COMPUTER_TOOL_USE_PREFIX}:'):
        parts = tool_use_id.split(':', 2)
        if len(parts) != 3:
            raise ValueError(f'Invalid OpenAI computer tool_use_id: {tool_use_id}')
        _, call_id, _ = parts
        return 'computer', call_id

    if tool_use_id.startswith(f'{OPENAI_FUNCTION_TOOL_USE_PREFIX}:'):
        _, call_id = tool_use_id.split(':', 1)
        return 'function', call_id

    raise ValueError(f'Unrecognized OpenAI tool_use_id: {tool_use_id}')


def _extract_tool_result_text_and_image(
    block: dict[str, Any],
) -> tuple[str, str | None]:
    text_content = ''
    image_data = None

    if block.get('is_error'):
        for content_item in block.get('content') or []:
            if isinstance(content_item, dict) and content_item.get('type') == 'text':
                text_content = str(content_item.get('text') or '')
                break
        return text_content, image_data

    for content_item in block.get('content') or []:
        if not isinstance(content_item, dict):
            continue
        if content_item.get('type') == 'text':
            text_content = str(content_item.get('text') or '')
        elif content_item.get('type') == 'image':
            source = content_item.get('source') or {}
            if source.get('type') == 'base64':
                image_data = str(source.get('data') or '')

    return text_content, image_data


def _convert_initial_messages(messages: list[BetaMessageParam]) -> list[dict[str, Any]]:
    response_messages: list[dict[str, Any]] = []

    for message in messages:
        role = str(message.get('role') or 'user')
        content = message.get('content')

        if isinstance(content, str):
            response_messages.append(
                {
                    'role': role,
                    'content': [{'type': 'input_text', 'text': content}],
                }
            )
            continue

        if not isinstance(content, list):
            continue

        parts: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get('type')
            if block_type == 'text':
                parts.append(
                    {'type': 'input_text', 'text': str(block.get('text') or '')}
                )
            elif block_type == 'image':
                source = block.get('source') or {}
                if source.get('type') == 'base64':
                    media_type = source.get('media_type') or 'image/png'
                    parts.append(
                        {
                            'type': 'input_image',
                            'image_url': f'data:{media_type};base64,{source.get("data", "")}',
                            'detail': 'original',
                        }
                    )

        if parts:
            response_messages.append({'role': role, 'content': parts})

    return response_messages


def build_openai_responses_request(
    messages: list[BetaMessageParam],
    provider_state: dict[str, Any] | None,
) -> OpenAIResponsesRequest:
    state = dict(provider_state or {})
    last_response_id = state.get('last_response_id')

    last_assistant_idx = -1
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].get('role') == 'assistant':
            last_assistant_idx = idx
            break

    if last_assistant_idx == -1:
        return OpenAIResponsesRequest(
            input_items=_convert_initial_messages(messages),
            previous_response_id=None,
            provider_state=state,
        )

    if not last_response_id:
        raise ValueError(
            'OpenAI Responses job cannot resume without provider_state.last_response_id'
        )

    trailing_messages = messages[last_assistant_idx + 1 :]
    input_items: list[dict[str, Any]] = []
    computer_groups: dict[str, dict[str, Any]] = {}
    computer_order: list[str] = []

    for message in trailing_messages:
        if message.get('role') != 'user':
            continue
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get('type') != 'tool_result':
                continue

            tool_use_id = str(block.get('tool_use_id') or '')
            try:
                tool_kind, call_id = parse_openai_tool_use_id(tool_use_id)
            except ValueError:
                logger.debug(f'Skipping non-OpenAI tool result id {tool_use_id}')
                continue

            text_content, image_data = _extract_tool_result_text_and_image(block)

            if tool_kind == 'function':
                input_items.append(
                    {
                        'type': 'function_call_output',
                        'call_id': call_id,
                        'output': text_content or 'Tool executed successfully',
                    }
                )
                continue

            if call_id not in computer_groups:
                computer_groups[call_id] = {'image_data': None}
                computer_order.append(call_id)

            if image_data:
                computer_groups[call_id]['image_data'] = image_data

    pending_safety_checks = state.get('pending_safety_checks') or []
    for call_id in computer_order:
        image_data = computer_groups[call_id].get('image_data')
        if not image_data:
            raise ValueError(
                f'OpenAI computer follow-up for call {call_id} is missing a screenshot'
            )

        computer_output: dict[str, Any] = {
            'type': 'computer_call_output',
            'call_id': call_id,
            'output': {
                'type': 'computer_screenshot',
                'image_url': f'data:image/png;base64,{image_data}',
                'detail': 'original',
            },
        }
        if pending_safety_checks:
            computer_output['acknowledged_safety_checks'] = pending_safety_checks
        input_items.append(computer_output)

    if pending_safety_checks:
        logger.info(f'Auto-acknowledging OpenAI safety checks: {pending_safety_checks}')
        state.pop('pending_safety_checks', None)

    return OpenAIResponsesRequest(
        input_items=input_items,
        previous_response_id=str(last_response_id),
        provider_state=state,
    )
