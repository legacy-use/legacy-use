"""PyAutoGUI conversion wrappers for the OpenCUA handler."""

from typing import Dict, Optional

from anthropic.types.beta import BetaToolUseBlockParam

from server.computer_use.handlers.utils.pyautogui_converter import (
    convert_pyautogui_code_to_tool_use as _convert_pyautogui_code_to_tool_use,
)
from server.computer_use.handlers.utils.pyautogui_converter import (
    extract_function_parameters as _extract_function_parameters,
)
from server.computer_use.handlers.utils.pyautogui_converter import (
    parse_task as _parse_task,
)

parse_task = _parse_task
extract_function_parameters = _extract_function_parameters


def convert_pyautogui_code_to_tool_use(
    code: str, latest_api_definitions: Optional[Dict[str, str]] = None
) -> BetaToolUseBlockParam:
    """Convert PyAutoGUI code to tool use with OpenCUA-specific ids."""
    return _convert_pyautogui_code_to_tool_use(
        code,
        latest_api_definitions,
        tool_id_prefix='toolu_opencua',
        default_wait_seconds=20,
        invalid_to_ui_not_as_expected=True,
    )
