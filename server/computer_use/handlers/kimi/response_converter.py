"""Response conversion utilities for Kimi Bedrock."""

from __future__ import annotations

import json
import re
from typing import Any

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
)

from server.computer_use.handlers.utils.key_mapping_utils import normalize_key_part
from server.computer_use.handlers.utils.pyautogui_converter import (
    convert_pyautogui_code_to_tool_use,
    extract_function_parameters,
    normalize_extraction_data,
    parse_task,
)
from server.computer_use.logging import logger


def _normalize_response_text(text: str) -> str:
    """Normalize common Kimi formatting quirks before parsing sections."""
    normalized = re.sub(r'</?think>', '\n', text, flags=re.IGNORECASE)
    normalized = re.sub(
        r'[ \t]+(##\s*(?:Thought|Action|Code):)',
        r'\n\1',
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized.strip()


def _split_code_commands(code: str) -> list[str]:
    """Split code into individual commands, preserving multiline calls."""
    commands: list[str] = []
    current: list[str] = []
    quote_char: str | None = None
    bracket_depth = 0
    index = 0

    while index < len(code):
        char = code[index]

        if quote_char:
            current.append(char)
            if char == '\\' and index + 1 < len(code):
                index += 1
                current.append(code[index])
            elif char == quote_char:
                quote_char = None
            index += 1
            continue

        if char in {'"', "'"}:
            quote_char = char
            current.append(char)
            index += 1
            continue

        if char in {'(', '[', '{'}:
            bracket_depth += 1
        elif char in {')', ']', '}'} and bracket_depth > 0:
            bracket_depth -= 1

        if char in {';', '\n'} and bracket_depth == 0:
            command = ''.join(current).strip()
            if command and not command.startswith('#'):
                commands.append(command)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    command = ''.join(current).strip()
    if command and not command.startswith('#'):
        commands.append(command)

    return commands


def _normalize_key_sequence(
    raw_commands: list[str], start_index: int
) -> tuple[list[str], int] | None:
    """Collapse keyDown/keyUp style sequences into supported press/hotkey actions."""
    commands: list[str] = []
    held_keys: list[str] = []
    pressed_keys: list[str] = []
    index = start_index
    consumed = False

    while index < len(raw_commands):
        command = raw_commands[index]

        if command.startswith('pyautogui.keyDown'):
            params = extract_function_parameters(command, ['key'])
            key = normalize_key_part(params.get('key', ''))
            if not key:
                break
            if key not in held_keys:
                held_keys.append(key)
            if key not in pressed_keys:
                pressed_keys.append(key)
            consumed = True
            index += 1
            continue

        if command.startswith('pyautogui.press'):
            params = extract_function_parameters(command, ['key'])
            key = normalize_key_part(params.get('key', ''))
            if not key:
                break
            pressed_keys.append(key)
            consumed = True
            index += 1
            continue

        if command.startswith('pyautogui.keyUp'):
            params = extract_function_parameters(command, ['key'])
            key = normalize_key_part(params.get('key', ''))
            if not key:
                break
            if key in held_keys:
                held_keys.remove(key)
            consumed = True
            index += 1
            continue

        break

    if not consumed or not pressed_keys:
        return None

    if len(pressed_keys) == 1:
        commands.append(f'pyautogui.press(key="{pressed_keys[0]}")')
    else:
        commands.append(f'pyautogui.hotkey(keys={json.dumps(pressed_keys)})')

    return commands, index


def _try_parse_raw_extraction(
    code: str, latest_api_definitions: dict[str, str] | None
) -> BetaContentBlockParam | None:
    """Interpret a raw JSON code block as the final extraction payload."""
    if 'pyautogui.' in code or 'computer.' in code:
        return None

    try:
        parsed = json.loads(code)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    try:
        extraction_data = normalize_extraction_data(parsed, latest_api_definitions)
    except ValueError as exc:
        return {
            'id': 'toolu_kimi_terminate',
            'type': 'tool_use',
            'name': 'ui_not_as_expected',
            'input': {'reasoning': str(exc)},
        }

    return {
        'id': 'toolu_kimi_extraction',
        'type': 'tool_use',
        'name': 'extraction',
        'input': {'data': extraction_data},
    }


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
    computer_options: dict[str, Any] | None = None,
) -> tuple[list[BetaContentBlockParam], str]:
    """Convert a Kimi response to Anthropic-style content blocks."""
    parsed_text = _normalize_response_text(_extract_text_from_response(response))
    logger.debug(f'Kimi raw response text: {parsed_text[:2000]}')
    task = parse_task(parsed_text)
    logger.debug(
        'Kimi parsed task: '
        f'thought={bool(task.get("thought"))}, '
        f'action={bool(task.get("action"))}, '
        f'code={task.get("code", "")[:1000] if task.get("code") else ""}'
    )

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

    logger.debug(f'Kimi model code block: {code}')

    raw_extraction = _try_parse_raw_extraction(code, latest_api_definitions)
    if raw_extraction is not None:
        logger.debug(
            f'Kimi model tool output mapped from raw JSON code block: {raw_extraction}'
        )
        content_blocks.append(raw_extraction)
        return content_blocks, 'end_turn'

    raw_commands = _split_code_commands(code)
    logger.debug(f'Kimi raw code commands: {raw_commands}')
    commands: list[str] = []
    index = 0
    while index < len(raw_commands):
        command = raw_commands[index]

        if command.startswith('pyautogui.keyDown'):
            normalized_sequence = _normalize_key_sequence(raw_commands, index)
            if normalized_sequence is not None:
                sequence_commands, next_index = normalized_sequence
                commands.extend(sequence_commands)
                index = next_index
                continue

        if command.startswith('pyautogui.keyUp'):
            up_params = extract_function_parameters(command, ['key'])
            up_key = normalize_key_part(up_params.get('key', ''))
            if up_key:
                commands.append(f'pyautogui.press(key="{up_key}")')
                index += 1
                continue

        commands.append(command)
        index += 1

    logger.debug(f'Kimi normalized commands: {commands}')

    for command in commands:
        tool_use = convert_pyautogui_code_to_tool_use(
            command,
            latest_api_definitions,
            computer_options=computer_options,
            tool_id_prefix='toolu_kimi',
            default_wait_seconds=20,
            invalid_to_ui_not_as_expected=True,
        )
        logger.debug(f'Kimi tool mapping: command={command} -> tool_use={tool_use}')
        content_blocks.append(tool_use)

        if tool_use['name'] in {'extraction', 'ui_not_as_expected'}:
            stop_reason = 'end_turn'
            break
        stop_reason = 'tool_use'

    return content_blocks, stop_reason
