"""PyAutoGUI to tool use conversion utilities for OpenCUA handler."""

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
    # Normalize newlines
    text = text.strip()

    # Step (optional, e.g. '# Step 1:')
    step_match = re.search(r'#\s*Step\s*([^\n:]+):?', text, re.IGNORECASE)
    step = f'{step_match.group(1).strip()}' if step_match else None

    # Thought
    thought_match = re.search(
        r'##\s*Thought:\s*(.*?)(?=##\s*Action:|##\s*Code:|$)',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    thought = thought_match.group(1).strip() if thought_match else None

    # Action
    action_match = re.search(
        r'##\s*Action:\s*(.*?)(?=##\s*Code:|$)', text, re.DOTALL | re.IGNORECASE
    )
    action = action_match.group(1).strip() if action_match else None

    # Code (inside fenced block or after "## Code:")
    code_match = re.search(
        r'##\s*Code:\s*```(?:python|code)?\n?(.*?)```',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not code_match:
        # fallback if no fenced block
        code_match = re.search(r'##\s*Code:\s*(.*)', text, re.DOTALL | re.IGNORECASE)
    code = code_match.group(1).strip() if code_match else None

    return {'step': step, 'thought': thought, 'action': action, 'code': code}


def extract_function_parameters(
    func_call: str, positional_keys: Optional[list[str]] = None
) -> Dict[str, str]:
    """Extract parameters from a function call string more robustly.

    Args:
        func_call: The function call string (e.g., "click(x=1, y=2)" or "scroll(-10)")
        positional_keys: List of keys to use for positional parameters (e.g., ['x', 'y'])

    Returns:
        Dictionary of parameter name -> value
    """
    # Find the parameter section between parentheses
    paren_start = func_call.find('(')
    paren_end = func_call.rfind(')')

    if paren_start == -1 or paren_end == -1:
        return {}

    params_str = func_call[paren_start + 1 : paren_end]
    if not params_str.strip():
        return {}

    # Check if this uses named parameters (contains '=')
    if '=' in params_str:
        # Handle named parameters (key=value style)
        params = {}
        i = 0
        while i < len(params_str):
            # Skip whitespace
            while i < len(params_str) and params_str[i].isspace():
                i += 1
            if i >= len(params_str):
                break

            # Find parameter name
            name_start = i
            while i < len(params_str) and params_str[i] not in '=':
                i += 1
            if i >= len(params_str):
                break

            param_name = params_str[name_start:i].strip()
            i += 1  # skip '='

            # Skip whitespace after =
            while i < len(params_str) and params_str[i].isspace():
                i += 1
            if i >= len(params_str):
                break

            # Extract parameter value (handle quotes and brackets)
            value_start = i
            if params_str[i] in ['"', "'"]:
                quote_char = params_str[i]
                i += 1  # skip opening quote
                value_start = i
                # Find closing quote, handling escapes
                while i < len(params_str):
                    if params_str[i] == quote_char:
                        break
                    if params_str[i] == '\\':
                        i += 1  # skip escaped character
                    i += 1
                value = params_str[value_start:i]
                i += 1  # skip closing quote
            elif params_str[i] == '[':
                # Handle list/array notation
                bracket_count = 1
                i += 1
                value_start = i - 1  # include opening bracket
                while i < len(params_str) and bracket_count > 0:
                    if params_str[i] == '[':
                        bracket_count += 1
                    elif params_str[i] == ']':
                        bracket_count -= 1
                    i += 1
                value = params_str[value_start:i]
            else:
                # Find end of value (comma or end of string)
                while i < len(params_str) and params_str[i] != ',':
                    i += 1
                value = params_str[value_start:i].strip()

            params[param_name] = value

            # Skip comma
            while i < len(params_str) and params_str[i] in ', ':
                i += 1

        return params
    else:
        # Handle positional parameters
        # Split by comma for multiple values, or return single value
        if ',' in params_str:
            # Multiple positional parameters
            values = [val.strip().strip('\'"') for val in params_str.split(',')]
        else:
            # Single positional parameter
            values = [params_str.strip().strip('\'"')]

        # Map to provided keys or default numeric keys
        params = {}
        if positional_keys:
            for i, value in enumerate(values):
                if i < len(positional_keys):
                    params[positional_keys[i]] = value
        else:
            # Use numeric keys as fallback
            for i, value in enumerate(values):
                params[str(i)] = value

        return params


def convert_pyautogui_code_to_tool_use(
    code: str, latest_api_definitions: Optional[Dict[str, str]] = None
) -> BetaToolUseBlockParam:
    """Convert PyAutoGUI code to tool use."""
    # extract command, these are either pyautogui.<command> or computer.<command>
    if 'pyautogui.' in code:
        command = code.split('pyautogui.')[1]
    elif 'computer.' in code:
        command = code.split('computer.')[1]
    else:
        raise ValueError(f'Unknown command: {code}')

    def _convert_coordinate(coordinate: str) -> tuple[int, int]:
        """Convert coordinate string to tuple of ints."""
        params = extract_function_parameters(coordinate, ['x', 'y'])
        x = int(params.get('x', '0'))
        y = int(params.get('y', '0'))
        return x, y

    def _construct_tool_use(action: str, **args: Any) -> BetaToolUseBlockParam:
        """Construct tool use."""
        return {
            'id': f'toolu_opencua_{action}',
            'type': 'tool_use',
            'name': 'computer',
            'input': {'action': action, **args},
        }

    if command.startswith('click'):
        # click(x=248, y=730)
        x, y = _convert_coordinate(command)
        return _construct_tool_use('left_click', coordinate=[x, y])
    elif command.startswith('rightClick'):
        # rightClick(x=248, y=730)
        x, y = _convert_coordinate(command)
        return _construct_tool_use('right_click', coordinate=[x, y])
    elif command.startswith('middleClick'):
        # middleClick(x=248, y=730)
        x, y = _convert_coordinate(command)
        return _construct_tool_use('middle_click', coordinate=[x, y])
    elif command.startswith('doubleClick'):
        # doubleClick(x=248, y=730)
        x, y = _convert_coordinate(command)
        return _construct_tool_use('double_click', coordinate=[x, y])
    elif command.startswith('tripleClick'):
        # tripleClick(x=248, y=730)
        x, y = _convert_coordinate(command)
        return _construct_tool_use('triple_click', coordinate=[x, y])
    elif command.startswith('moveTo'):
        # moveTo(x=248, y=730)
        x, y = _convert_coordinate(command)
        return _construct_tool_use('mouse_move', coordinate=[x, y])
    elif command.startswith('dragTo'):
        # dragTo(x=248, y=730)
        x, y = _convert_coordinate(command)
        return _construct_tool_use('left_click_drag', coordinate=[x, y])
    elif command.startswith('scroll'):
        # scroll(-10) or scroll(amount=-10)
        params = extract_function_parameters(command, ['amount'])
        scroll_amount = params.get('amount', '0')
        return _construct_tool_use(
            'scroll', scroll_direction='up', scroll_amount=scroll_amount
        )
    elif command.startswith('hscroll'):
        # hscroll(10) or hscroll(amount=10)
        params = extract_function_parameters(command, ['amount'])
        scroll_amount = params.get('amount', '0')
        return _construct_tool_use(
            'scroll', scroll_direction='left', scroll_amount=scroll_amount
        )
    elif command.startswith('write'):
        # write(message='Hello, world!')
        params = extract_function_parameters(command)
        text = params.get('message', '')
        return _construct_tool_use('type', text=text)
    elif command.startswith('press'):
        # press('esc') or press(key='esc')
        params = extract_function_parameters(command, ['key'])
        key = params.get('key', '')
        normalized_key = normalize_key_part(key)
        return _construct_tool_use('key', text=normalized_key)
    elif command.startswith('hotkey'):
        # hotkey(['ctrl', 'alt', 'delete']) or hotkey(keys=['ctrl', 'alt', 'delete'])
        params = extract_function_parameters(command, ['keys'])
        keys_str = params.get('keys', '[]')

        # Parse the keys array (handle both ['a', 'b'] and ["a", "b"] formats)
        keys_str = keys_str.strip('[]')
        if keys_str:
            keys = [key.strip().strip('\'"') for key in keys_str.split(',')]
        else:
            keys = []

        normalized_keys = [normalize_key_part(key) for key in keys]
        return _construct_tool_use('key', text='+'.join(normalized_keys))
    elif command.startswith('wait'):
        # wait(seconds=1) or wait(1)
        params = extract_function_parameters(command, ['seconds'])
        seconds = params.get('seconds', '0')
        return _construct_tool_use('wait', duration=float(seconds))
    elif command.startswith('terminate'):
        # terminate(status='success', data='{...}')
        params = extract_function_parameters(command)
        status = params.get('status', 'failure')
        data_str = params.get('data', '{}')

        # Try to parse data as JSON
        data = data_str
        if data_str:
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning(f'Invalid JSON in data: {data_str}')
                # Keep as string if JSON parsing fails

        if status == 'success':
            name = ''
            if latest_api_definitions:
                name = latest_api_definitions['api_name']

            return {
                'id': 'toolu_opencua_terminate',
                'type': 'tool_use',
                'name': 'extraction',
                'input': {'data': {'name': name, 'result': data}},
            }
        else:
            # handle if data is not a dict
            if not isinstance(data, dict) or 'reasoning' not in data:
                data = {'reasoning': data}

            return {
                'id': 'toolu_opencua_terminate',
                'type': 'tool_use',
                'name': 'ui_not_as_expected',
                'input': {'data': {'reasoning': data['reasoning']}},
            }

    raise ValueError(f'Unknown command: {command}')
