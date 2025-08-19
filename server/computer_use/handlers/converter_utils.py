"""Stateless converters for messages, tools, and provider output."""

from __future__ import annotations

from typing import Any, List

from openai.types.chat import (
    ChatCompletionToolParam,
)

from server.computer_use.tools.base import BaseAnthropicTool

# Key normalization mappings for computer tools
KEY_ALIASES = {
    'Escape': {'esc', 'escape'},
    'Return': {'enter', 'return'},
    'Super_L': {'win', 'windows', 'super', 'meta', 'cmd', 'super_l', 'super_r'},
    'BackSpace': {'backspace'},
    'Delete': {'del', 'delete'},
    'Tab': {'tab'},
    'space': {'space'},
    'Page_Up': {'pageup'},
    'Page_Down': {'pagedown'},
    'Home': {'home'},
    'End': {'end'},
    'Up': {'up'},
    'Down': {'down'},
    'Left': {'left'},
    'Right': {'right'},
    'Print': {'printscreen', 'prtsc'},
    'ctrl': {'ctrl', 'control', 'ctrl_l', 'ctrl_r'},
    'shift': {'shift', 'shift_l', 'shift_r'},
    'alt': {'alt', 'alt_l', 'alt_r', 'option'},
}


def normalize_key_part(part: str) -> str:
    """
    Normalize a single key part.

    Args:
        part: Single key part to normalize

    Returns:
        Normalized key string
    """
    low = part.lower()

    # Check key aliases - find canonical form for any alias
    for canonical, aliases in KEY_ALIASES.items():
        if low in aliases:
            return canonical

    # Function keys
    if low.startswith('f') and low[1:].isdigit():
        return f'F{int(low[1:])}'

    # Single letters or digits: keep as-is
    if len(part) == 1:
        return part

    return part


def normalize_key_combo(combo: str) -> str:
    """
    Normalize key combinations for xdotool compatibility.

    Args:
        combo: Key combination string (e.g., 'ctrl+c', 'alt+tab')

    Returns:
        Normalized key combination string
    """
    if not isinstance(combo, str):
        return combo

    parts = [p.strip() for p in combo.replace(' ', '').split('+') if p.strip()]
    normalized = [normalize_key_part(p) for p in parts]
    return '+'.join(normalized)


def _spec_to_openai_chat_function(spec: dict[str, Any]) -> ChatCompletionToolParam:
    name = str(spec.get('name') or '')
    description = str(spec.get('description') or f'Tool: {name}')
    parameters = spec.get('input_schema') or {'type': 'object', 'properties': {}}
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': parameters,
        },
    }


def expand_computer_to_openai_chat_functions(
    tool: BaseAnthropicTool,
) -> List[ChatCompletionToolParam]:
    spec = tool.internal_spec()
    actions: list[dict] = spec.get('actions') or []
    funcs: List[ChatCompletionToolParam] = []
    for action in actions:
        aname = str(action.get('name') or '')
        params = action.get('params') or {}
        required = action.get('required') or []
        description = action.get('description') or f'Computer action: {aname}'
        funcs.append(
            {
                'type': 'function',
                'function': {
                    'name': aname,
                    'description': description,
                    'parameters': {
                        'type': 'object',
                        'properties': params,
                        'required': required,
                    },
                },
            }
        )
    return funcs


def internal_specs_to_openai_chat_functions(
    tools: List[BaseAnthropicTool],
) -> List[ChatCompletionToolParam]:
    result: List[ChatCompletionToolParam] = []
    for tool in tools:
        if getattr(tool, 'name', None) == 'computer':
            result.extend(expand_computer_to_openai_chat_functions(tool))
        else:
            result.append(_spec_to_openai_chat_function(tool.internal_spec()))
    return result
