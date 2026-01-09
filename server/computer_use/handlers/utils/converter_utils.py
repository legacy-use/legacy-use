"""Stateless converters for messages, tools, and provider output."""

from __future__ import annotations

from typing import Any, List

from openai.types.chat import (
    ChatCompletionToolParam,
)

from server.computer_use.tools.base import BaseAnthropicTool


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


# --- Gemini Converters ---


def _spec_to_gemini_function(spec: dict[str, Any]) -> dict[str, Any]:
    """Convert internal tool spec to Gemini function declaration format."""
    name = str(spec.get('name') or '')
    description = str(spec.get('description') or f'Tool: {name}')
    parameters = spec.get('input_schema') or {'type': 'object', 'properties': {}}

    return {
        'name': name,
        'description': description,
        'parameters': parameters,
    }


def expand_computer_to_gemini_functions(
    tool: BaseAnthropicTool,
) -> List[dict[str, Any]]:
    """Expand computer tool to individual Gemini function declarations for each action."""
    spec = tool.internal_spec()
    actions: list[dict] = spec.get('actions') or []
    funcs: List[dict[str, Any]] = []

    for action in actions:
        aname = str(action.get('name') or '')
        params = action.get('params') or {}
        required = action.get('required') or []
        description = action.get('description') or f'Computer action: {aname}'

        funcs.append(
            {
                'name': aname,
                'description': description,
                'parameters': {
                    'type': 'object',
                    'properties': params,
                    'required': required,
                },
            }
        )

    return funcs


def internal_specs_to_gemini_functions(
    tools: List[BaseAnthropicTool],
) -> List[dict[str, Any]]:
    """Convert internal tool specs to Gemini function declarations."""
    result: List[dict[str, Any]] = []
    for tool in tools:
        if getattr(tool, 'name', None) == 'computer':
            result.extend(expand_computer_to_gemini_functions(tool))
        else:
            result.append(_spec_to_gemini_function(tool.internal_spec()))
    return result
