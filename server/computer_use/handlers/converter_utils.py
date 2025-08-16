"""Stateless converters for messages, tools, and provider output.

Handlers should call these pure helpers to keep logic DRY and testable.
"""

from __future__ import annotations

from typing import Any, List, cast


from openai.types.chat import (
    ChatCompletionToolParam,
)

from server.computer_use.tools.base import BaseAnthropicTool


def _spec_to_openai_chat_function(spec: dict) -> ChatCompletionToolParam:
    name = str(spec.get('name') or '')
    description = str(spec.get('description') or f'Tool: {name}')
    parameters = cast(
        dict[str, Any], spec.get('input_schema') or {'type': 'object', 'properties': {}}
    )
    return cast(
        ChatCompletionToolParam,
        {
            'type': 'function',
            'function': {
                'name': name,
                'description': description,
                'parameters': parameters,
            },
        },
    )


def expand_computer_to_openai_chat_functions(
    tool: BaseAnthropicTool,
) -> List[ChatCompletionToolParam]:
    spec = tool.internal_spec()
    actions: list[dict] = cast(list[dict], spec.get('actions') or [])
    funcs: List[ChatCompletionToolParam] = []
    for action in actions:
        aname = str(action.get('name') or '')
        params = cast(dict[str, Any], action.get('params') or {})
        funcs.append(
            cast(
                ChatCompletionToolParam,
                {
                    'type': 'function',
                    'function': {
                        'name': aname,
                        'description': f'Computer action: {aname}',
                        'parameters': {
                            'type': 'object',
                            'properties': params,
                            'required': [],
                        },
                    },
                },
            )
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
