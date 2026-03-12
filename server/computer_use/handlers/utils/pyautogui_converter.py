"""Shared utilities for parsing GUI-agent text output and PyAutoGUI code."""

from __future__ import annotations

import ast
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
    text = re.sub(r'</?think>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(
        r'[ \t]+(##\s*(?:Thought|Action|Code):)',
        r'\n\1',
        text,
        flags=re.IGNORECASE,
    )
    text = text.strip()

    step_match = re.search(r'#\s*Step\s*([^\n:]+):?', text, re.IGNORECASE)
    step = f'{step_match.group(1).strip()}' if step_match else None

    section_pattern = re.compile(
        r'(?:^|\n)(?:##\s*)?(Thought|Action|Code):',
        re.IGNORECASE,
    )
    section_matches = list(section_pattern.finditer(text))

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(section_matches):
        section_type = match.group(1).lower()
        content_start = match.end()
        content_end = (
            section_matches[index + 1].start()
            if index + 1 < len(section_matches)
            else len(text)
        )
        content = text[content_start:content_end].strip()

        if section_type == 'code':
            fenced_match = re.fullmatch(
                r'```(?:python|code)?\n?(.*?)```',
                content,
                re.DOTALL | re.IGNORECASE,
            )
            if fenced_match:
                content = fenced_match.group(1).strip()

        sections.append((section_type, content))

    code = None
    thought = None
    action = None

    selected_code_index = None
    for index in range(len(sections) - 1, -1, -1):
        section_type, content = sections[index]
        if section_type == 'code' and content:
            selected_code_index = index
            code = content
            break

    if selected_code_index is not None:
        for index in range(selected_code_index - 1, -1, -1):
            section_type, content = sections[index]
            if thought is None and section_type == 'thought' and content:
                thought = content
            if action is None and section_type == 'action' and content:
                action = content
            if thought is not None and action is not None:
                break
    else:
        for section_type, content in reversed(sections):
            if thought is None and section_type == 'thought' and content:
                thought = content
            if action is None and section_type == 'action' and content:
                action = content
            if thought is not None and action is not None:
                break

    return {'step': step, 'thought': thought, 'action': action, 'code': code}


def extract_function_parameters(
    func_call: str, positional_keys: Optional[list[str]] = None
) -> Dict[str, str]:
    """Extract parameters from a function call string."""

    def _stringify_value(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if value is None:
            return 'null'
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    try:
        expression = ast.parse(func_call.strip(), mode='eval')
        call = expression.body
        if isinstance(call, ast.Call):
            params: Dict[str, str] = {}

            for index, arg in enumerate(call.args):
                value = _stringify_value(ast.literal_eval(arg))
                if positional_keys and index < len(positional_keys):
                    params[positional_keys[index]] = value
                else:
                    params[str(index)] = value

            for keyword in call.keywords:
                if keyword.arg is None:
                    continue
                params[keyword.arg] = _stringify_value(ast.literal_eval(keyword.value))

            return params
    except (SyntaxError, ValueError, TypeError):
        pass

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


def normalize_extraction_data(
    data: Any,
    latest_api_definitions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Normalize model-provided extraction payloads to the expected schema shape."""

    def _parse_example_result() -> Any:
        if not latest_api_definitions:
            return None
        raw_example = (latest_api_definitions.get('api_response_example') or '').strip()
        if not raw_example:
            return None
        try:
            return json.loads(raw_example)
        except json.JSONDecodeError:
            logger.warning(f'Invalid API response example JSON: {raw_example}')
            return None

    def _unwrap_named_result(value: Any, expected_name: str) -> Any:
        while (
            isinstance(value, dict)
            and 'name' in value
            and 'result' in value
            and (
                not expected_name
                or str(value.get('name') or '').strip() == expected_name
            )
        ):
            value = value['result']
        return value

    def _coerce_to_example_shape(example: Any, value: Any) -> Any:
        if example is None:
            return value

        if isinstance(example, dict):
            value = _unwrap_named_result(value, expected_name='')
            if isinstance(value, dict):
                if set(value.keys()) == set(example.keys()):
                    return {
                        key: _coerce_to_example_shape(example[key], value[key])
                        for key in example
                    }
                if len(example) == 1 and len(value) == 1:
                    only_key = next(iter(example))
                    only_value = next(iter(value.values()))
                    return {
                        only_key: _coerce_to_example_shape(
                            example[only_key], only_value
                        )
                    }
            if len(example) == 1:
                only_key = next(iter(example))
                return {only_key: _coerce_to_example_shape(example[only_key], value)}
            return value

        if isinstance(example, list):
            if isinstance(value, dict):
                if len(value) == 1:
                    value = next(iter(value.values()))
                else:
                    list_candidates = [
                        (str(key), item)
                        for key, item in value.items()
                        if isinstance(item, list)
                    ]
                    if list_candidates:
                        preferred_candidate = next(
                            (
                                item
                                for key, item in list_candidates
                                if key.lower()
                                in {
                                    'result',
                                    'results',
                                    'item',
                                    'items',
                                    'entry',
                                    'entries',
                                    'search_result',
                                    'search_results',
                                    'settings_search_results',
                                }
                                or 'result' in key.lower()
                                or 'entry' in key.lower()
                            ),
                            None,
                        )
                        value = preferred_candidate or list_candidates[0][1]
            if not isinstance(value, list):
                return value
            if not example:
                return value
            return [_coerce_to_example_shape(example[0], item) for item in value]

        if isinstance(value, dict) and len(value) == 1:
            return _coerce_to_example_shape(example, next(iter(value.values())))
        return value

    expected_name = ''
    if latest_api_definitions:
        expected_name = str(latest_api_definitions.get('api_name') or '').strip()

    raw_name = expected_name
    raw_result = data
    if isinstance(data, dict) and 'name' in data and 'result' in data:
        raw_name = str(data.get('name') or raw_name).strip() or raw_name
        raw_result = data.get('result')

    if expected_name and raw_name and raw_name != expected_name:
        raise ValueError(
            f'Extraction name `{raw_name}` does not match expected API name `{expected_name}`'
        )

    raw_result = _unwrap_named_result(raw_result, raw_name or expected_name)
    expected_result_example = _parse_example_result()
    normalized_result = _coerce_to_example_shape(expected_result_example, raw_result)

    return {
        'name': raw_name,
        'result': normalized_result,
    }


def convert_pyautogui_code_to_tool_use(
    code: str,
    latest_api_definitions: Optional[Dict[str, str]] = None,
    *,
    computer_options: Optional[Dict[str, Any]] = None,
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
        elif 'time.' in code:
            command = code.split('time.', 1)[1].strip()
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

        def _convert_coordinate(coordinate: str) -> tuple[int, int]:
            params = extract_function_parameters(coordinate, ['x', 'y'])
            if 'x' not in params or 'y' not in params:
                raise ValueError(f'Missing x/y coordinates in `{coordinate}`')
            x = _normalize_coordinate_value(params['x'], axis='x')
            y = _normalize_coordinate_value(params['y'], axis='y')
            if x < 0 or y < 0:
                raise ValueError(
                    f'Negative coordinates are not allowed in `{coordinate}`'
                )
            if x == 0 and y == 0:
                raise ValueError(
                    f'Placeholder coordinate (0, 0) is not allowed in `{coordinate}`'
                )
            return x, y

        def _normalize_coordinate_value(raw_value: str, *, axis: str) -> int:
            value = float(raw_value)
            if 0 < value <= 1:
                display_key = 'display_width_px' if axis == 'x' else 'display_height_px'
                display_size = None
                if computer_options:
                    display_size = computer_options.get(display_key)
                if display_size is None:
                    raise ValueError(
                        f'Normalized {axis} coordinate `{raw_value}` requires display metadata'
                    )
                return int(round(value * float(display_size)))
            return int(value)

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

        def _click_action_from_params(params: Dict[str, str]) -> str:
            button = str(params.get('button') or 'left').strip().lower()
            clicks = int(float(params.get('clicks') or '1'))

            if button == 'left':
                if clicks <= 1:
                    return 'left_click'
                if clicks == 2:
                    return 'double_click'
                if clicks == 3:
                    return 'triple_click'
                raise ValueError(f'Unsupported click count `{clicks}` for `{command}`')

            if clicks != 1:
                raise ValueError(
                    f'Unsupported click count `{clicks}` for button `{button}` in `{command}`'
                )

            if button == 'right':
                return 'right_click'
            if button == 'middle':
                return 'middle_click'

            raise ValueError(f'Unsupported click button `{button}` in `{command}`')

        if command.startswith('click'):
            params = extract_function_parameters(command, ['x', 'y'])
            x, y = _convert_coordinate(command)
            return _construct_tool_use(
                _click_action_from_params(params),
                coordinate=[x, y],
            )
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
            params = extract_function_parameters(command, ['message'])
            text_value = (
                params.get('message') or params.get('text') or params.get('value') or ''
            )
            if not text_value:
                raise ValueError(f'Missing text in `{command}`')
            return _construct_tool_use('type', text=text_value)
        if command.startswith('press'):
            params = extract_function_parameters(command, ['key'])
            normalized_key = normalize_key_part(params.get('key', ''))
            if not normalized_key:
                raise ValueError(f'Missing key in `{command}`')
            return _construct_tool_use('key', text=normalized_key)
        if command.startswith('hotkey'):
            params = extract_function_parameters(command, ['keys'])
            extra_positional_keys = [
                params[key]
                for key in sorted(
                    (key for key in params if key.isdigit()),
                    key=lambda value: int(value),
                )
            ]
            keys_raw = params.get('keys', '[]').strip()
            if extra_positional_keys:
                keys = [
                    normalize_key_part(part)
                    for part in [params.get('keys', ''), *extra_positional_keys]
                    if part
                ]
            elif keys_raw.startswith('[') and keys_raw.endswith(']'):
                keys = [
                    normalize_key_part(key.strip().strip('\'"'))
                    for key in keys_raw.strip('[]').split(',')
                    if key.strip()
                ]
            else:
                keys = [
                    normalize_key_part(part) for part in keys_raw.split('+') if part
                ]
            if not keys:
                raise ValueError(f'Missing keys in `{command}`')
            return _construct_tool_use('key', text='+'.join(keys))
        if command.startswith('sleep'):
            params = extract_function_parameters(command, ['seconds'])
            seconds = params.get('seconds')
            duration = float(seconds) if seconds else float(default_wait_seconds)
            return _construct_tool_use('wait', duration=duration)
        if command.startswith('wait'):
            params = extract_function_parameters(command, ['seconds'])
            seconds = params.get('seconds')
            duration = float(seconds) if seconds else float(default_wait_seconds)
            return _construct_tool_use('wait', duration=duration)
        if command.startswith('custom_action'):
            params = extract_function_parameters(command)
            action_name = params.get('action_name', '').strip()
            if not action_name:
                raise ValueError(f'Missing action_name in `{command}`')
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
                extraction_data = normalize_extraction_data(
                    data,
                    latest_api_definitions,
                )
                return {
                    'id': f'{tool_id_prefix}_extraction',
                    'type': 'tool_use',
                    'name': 'extraction',
                    'input': {'data': extraction_data},
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
