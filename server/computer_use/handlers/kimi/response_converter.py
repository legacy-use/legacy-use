"""Response conversion utilities for Kimi Bedrock."""

from __future__ import annotations

from typing import Any

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
)

from server.computer_use.handlers.utils.pyautogui_converter import (
    convert_pyautogui_code_to_tool_use,
    parse_task,
)


def _extract_text_from_response(response: Any) -> str:
    choices = response.get('choices') or []
    if not choices:
        return ''

    message = choices[0].get('message') or {}
    content = message.get('content')

    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ''

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get('type') == 'text':
            parts.append(str(item.get('text') or ''))
        elif 'text' in item:
            parts.append(str(item.get('text') or ''))

    return '\n'.join(part for part in parts if part).strip()


def convert_kimi_to_anthropic_response(
    response: dict[str, Any],
    latest_api_definitions: dict[str, str] | None = None,
) -> tuple[list[BetaContentBlockParam], str]:
    """Convert a Kimi response to Anthropic-style content blocks."""
    parsed_text = _extract_text_from_response(response)
    task = parse_task(parsed_text)

    content_blocks: list[BetaContentBlockParam] = []
    synthesized_parts: list[str] = []
    if task['step']:
        synthesized_parts.append(f'# Step: {task["step"]}')
    if task['thought']:
        synthesized_parts.append(f'## Thought:\n{task["thought"]}')
    if task['action']:
        synthesized_parts.append(f'## Action:\n{task["action"]}')
    if not synthesized_parts and parsed_text:
        synthesized_parts.append(parsed_text)

    if synthesized_parts:
        content_blocks.append(
            BetaTextBlockParam(type='text', text='\n'.join(synthesized_parts))
        )

    stop_reason = 'end_turn'
    code = task.get('code')
    if not code:
        return content_blocks, stop_reason

    for command in code.split('\n'):
        command = command.strip()
        if not command:
            continue

        tool_use = convert_pyautogui_code_to_tool_use(
            command,
            latest_api_definitions,
            tool_id_prefix='toolu_kimi',
            default_wait_seconds=20,
            invalid_to_ui_not_as_expected=True,
        )
        content_blocks.append(tool_use)

        if tool_use['name'] in {'extraction', 'ui_not_as_expected'}:
            stop_reason = 'end_turn'
            break
        stop_reason = 'tool_use'

    return content_blocks, stop_reason
