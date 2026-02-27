"""Shared utilities for parsing GUI-agent text output and PyAutoGUI code."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from anthropic.types.beta import BetaToolUseBlockParam

from server.computer_use.handlers.utils.key_mapping_utils import (
    normalize_key_part,
)

logger = logging.getLogger(__name__)


def parse_task(text: str) -> Dict[str, Optional[str]]:
    """Parse task response text into structured components."""
    text = text.strip()

    step_match = re.search(r'#\s*Step\s*([^\n:]+):?', text, re.IGNORECASE)
    step = f'{step_match.group(1).strip()}' if step_match else None

    thought_match = re.search(
        r'(?:^|\n)(?:##\s*)?Thought:\s*(.*?)(?=(?:\n(?:##\s*)?Action:)|(?:\n(?:##\s*)?Code:)|$)',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    thought = thought_match.group(1).strip() if thought_match else None

    action_match = re.search(
        r'(?:^|\n)(?:##\s*)?Action:\s*(.*?)(?=(?:\n(?:##\s*)?Code:)|$)',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    action = action_match.group(1).strip() if action_match else None

    code_match = re.search(
        r'(?:^|\n)(?:##\s*)?Code:\s*```(?:python|code)?\n?(.*?)```',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not code_match:
        code_match = re.search(
            r'(?:^|\n)(?:##\s*)?Code:\s*(.*)',
            text,
            re.DOTALL | re.IGNORECASE,
        )
    code = code_match.group(1).strip() if code_match else None

    return {'step': step, 'thought': thought, 'action': action, 'code': code}


def extract_function_parameters(
    func_call: str, positional_keys: Optional[list[str]] = None
) -> Dict[str, str]:
    """Extract parameters from a function call string."""
    paren_start = func_call.find('(')
    paren_end = func_call.rfind(')')

    if paren_start == -1 or paren_end == -1:
        return {}

    params_str = func_call[paren_start + 1 : paren_end]
    if not params_str.strip():
        return {}

    if '=' in params_str:
        params = {}
        i = 0
        while i < len(params_str):
            while i < len(params_str) and params_str[i].isspace():
                i += 1
            if i >= len(params_str):
                break

            name_start = i
            while i < len(params_str) and params_str[i] != '=':
                i += 1
            if i >= len(params_str):
                break

            param_name = params_str[name_start:i].strip()
            i += 1

            while i < len(params_str) and params_str[i].isspace():
                i += 1
            if i >= len(params_str):
                break

            value_start = i
            if params_str[i] in ['"', "'"]:
                quote_char = params_str[i]
                i += 1
                value_start = i
                while i < len(params_str):
                    if params_str[i] == quote_char:
                        break
                    if params_str[i] == '\\':
                        i += 1
                    i += 1
                value = params_str[value_start:i]
                i += 1
            elif params_str[i] in ['[', '{']:
                open_char = params_str[i]
                close_char = ']' if open_char == '[' else '}'
                depth = 1
                i += 1
                value_start = i - 1
                while i < len(params_str) and depth > 0:
                    if params_str[i] == open_char:
                        depth += 1
                    elif params_str[i] == close_char:
                        depth -= 1
                    i += 1
                value = params_str[value_start:i]
            else:
                while i < len(params_str) and params_str[i] != ',':
                    i += 1
                value = params_str[value_start:i].strip()

            params[param_name] = value

            while i < len(params_str) and params_str[i] in ', ':
                i += 1

        return params

    if ',' in params_str:
        values = [val.strip().strip('\'"') for val in params_str.split(',')]
    else:
        values = [params_str.strip().strip('\'"')]

    params = {}
    if positional_keys:
        for index, value in enumerate(values):
            if index < len(positional_keys):
                params[positional_keys[index]] = value
    else:
        for index, value in enumerate(values):
            params[str(index)] = value

    return params


def convert_pyautogui_code_to_tool_use(
    code: str,
    latest_api_definitions: Optional[Dict[str, str]] = None,
    *,
    tool_id_prefix: str = 'toolu_code',
    default_wait_seconds: int | float = 20,
    invalid_to_ui_not_as_expected: bool = True,
) -> BetaToolUseBlockParam:
    """Convert PyAutoGUI-like code to an internal tool use block."""

    def _make_ui_not_as_expected(reasoning: str) -> BetaToolUseBlockParam:
        return {
            'id': f'{tool_id_prefix}_terminate',
            'type': 'tool_use',
            'name': 'ui_not_as_expected',
            'input': {'reasoning': reasoning},
        }

    try:
        if 'pyautogui.' in code:
            command = code.split('pyautogui.', 1)[1].strip()
        elif 'computer.' in code:
            command = code.split('computer.', 1)[1].strip()
        else:
            raise ValueError(f'Unknown command: {code}')

        def _parse_json_value(raw_value: str, *, warning_context: str) -> Any:
            try:
                return json.loads(raw_value)
            except json.JSONDecodeError:
                try:
                    return json.loads(
                        raw_value.encode('utf-8').decode('unicode_escape')
                    )
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.warning(f'Invalid JSON in {warning_context}: {raw_value}')
                    raise

        def _to_int(value: str) -> int:
            return int(float(value))

        def _convert_coordinate(coordinate: str) -> tuple[int, int]:
            params = extract_function_parameters(coordinate, ['x', 'y'])
            x = _to_int(params.get('x', '0'))
            y = _to_int(params.get('y', '0'))
            return x, y

        def _construct_tool_use(action: str, **args: Any) -> BetaToolUseBlockParam:
            return {
                'id': f'{tool_id_prefix}_{action}',
                'type': 'tool_use',
                'name': 'computer',
                'input': {'action': action, **args},
            }

        def _parse_signed_amount(
            raw_value: str,
            *,
            positive_direction: str,
            negative_direction: str,
        ) -> tuple[str, int]:
            value = int(float(raw_value or '0'))
            if value < 0:
                return negative_direction, abs(value)
            return positive_direction, abs(value)

        if command.startswith('click'):
            x, y = _convert_coordinate(command)
            return _construct_tool_use('left_click', coordinate=[x, y])
        if command.startswith('rightClick'):
            x, y = _convert_coordinate(command)
            return _construct_tool_use('right_click', coordinate=[x, y])
        if command.startswith('middleClick'):
            x, y = _convert_coordinate(command)
            return _construct_tool_use('middle_click', coordinate=[x, y])
        if command.startswith('doubleClick'):
            x, y = _convert_coordinate(command)
            return _construct_tool_use('double_click', coordinate=[x, y])
        if command.startswith('tripleClick'):
            x, y = _convert_coordinate(command)
            return _construct_tool_use('triple_click', coordinate=[x, y])
        if command.startswith('moveTo'):
            x, y = _convert_coordinate(command)
            return _construct_tool_use('mouse_move', coordinate=[x, y])
        if command.startswith('dragTo'):
            x, y = _convert_coordinate(command)
            return _construct_tool_use('left_click_drag', coordinate=[x, y])
        if command.startswith('scroll'):
            params = extract_function_parameters(command, ['amount'])
            direction, amount = _parse_signed_amount(
                params.get('amount', '0'),
                positive_direction='up',
                negative_direction='down',
            )
            return _construct_tool_use(
                'scroll',
                scroll_direction=direction,
                scroll_amount=amount,
            )
        if command.startswith('hscroll'):
            params = extract_function_parameters(command, ['amount'])
            direction, amount = _parse_signed_amount(
                params.get('amount', '0'),
                positive_direction='right',
                negative_direction='left',
            )
            return _construct_tool_use(
                'scroll',
                scroll_direction=direction,
                scroll_amount=amount,
            )
        if command.startswith('write'):
            params = extract_function_parameters(command)
            return _construct_tool_use('type', text=params.get('message', ''))
        if command.startswith('press'):
            params = extract_function_parameters(command, ['key'])
            normalized_key = normalize_key_part(params.get('key', ''))
            return _construct_tool_use('key', text=normalized_key)
        if command.startswith('hotkey'):
            params = extract_function_parameters(command, ['keys'])
            keys_raw = params.get('keys', '[]').strip()
            if keys_raw.startswith('[') and keys_raw.endswith(']'):
                keys = [
                    normalize_key_part(key.strip().strip('\'"'))
                    for key in keys_raw.strip('[]').split(',')
                    if key.strip()
                ]
            else:
                keys = [
                    normalize_key_part(part) for part in keys_raw.split('+') if part
                ]
            return _construct_tool_use('key', text='+'.join(keys))
        if command.startswith('wait'):
            params = extract_function_parameters(command, ['seconds'])
            seconds = params.get('seconds')
            duration = float(seconds) if seconds else float(default_wait_seconds)
            return _construct_tool_use('wait', duration=duration)
        if command.startswith('custom_action'):
            params = extract_function_parameters(command)
            action_name = params.get('action_name', '').strip()
            input_parameters_raw = params.get('input_parameters', '{}')
            input_parameters: dict[str, Any] = {}
            if input_parameters_raw:
                try:
                    parsed = _parse_json_value(
                        input_parameters_raw,
                        warning_context='custom_action input_parameters',
                    )
                    if isinstance(parsed, dict):
                        input_parameters = parsed
                except json.JSONDecodeError:
                    pass
            tool_input: dict[str, Any] = {'action_name': action_name}
            if input_parameters:
                tool_input['input_parameters'] = input_parameters
            return {
                'id': f'{tool_id_prefix}_custom_action',
                'type': 'tool_use',
                'name': 'custom_action',
                'input': tool_input,
            }
        if command.startswith('terminate'):
            params = extract_function_parameters(command)
            status = params.get('status', 'failure')
            data_str = params.get('data') or params.get('answer', '{}')
            data: Any = data_str
            if data_str:
                try:
                    data = _parse_json_value(data_str, warning_context='terminate data')
                except json.JSONDecodeError:
                    pass

            if status == 'success':
                name = ''
                if latest_api_definitions:
                    name = latest_api_definitions.get('api_name', '')
                return {
                    'id': f'{tool_id_prefix}_extraction',
                    'type': 'tool_use',
                    'name': 'extraction',
                    'input': {'data': {'name': name, 'result': data}},
                }

            if not isinstance(data, dict) or 'reasoning' not in data:
                data = {'reasoning': data}
            return {
                'id': f'{tool_id_prefix}_terminate',
                'type': 'tool_use',
                'name': 'ui_not_as_expected',
                'input': {'reasoning': str(data.get('reasoning', 'Unknown error'))},
            }

        raise ValueError(f'Unknown command: {command}')
    except Exception as exc:
        if invalid_to_ui_not_as_expected:
            return _make_ui_not_as_expected(
                f'Failed to parse model action `{code}`: {exc}'
            )
        raise
