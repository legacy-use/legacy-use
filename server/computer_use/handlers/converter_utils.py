"""Stateless converters for messages, tools, and provider output.

Handlers should call these pure helpers to keep logic DRY and testable.
"""

from __future__ import annotations

from typing import Any, List, cast

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)
from openai.types.chat import (
    ChatCompletionToolParam,
)
from openai.types.responses import (
    ComputerToolParam,
    FunctionToolParam,
    Response,
    ResponseInputParam,
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


def _spec_to_openai_responses_function(spec: dict) -> FunctionToolParam:
    """Convert a tool spec to OpenAI Responses API function format."""
    name = str(spec.get('name') or '')
    description = str(spec.get('description') or f'Tool: {name}')
    parameters = cast(
        dict[str, Any], spec.get('input_schema') or {'type': 'object', 'properties': {}}
    )
    return cast(
        FunctionToolParam,
        {
            'type': 'function',
            'name': name,
            'description': description,
            'parameters': parameters,
        },
    )


def internal_specs_to_openai_responses_functions(
    tools: List[BaseAnthropicTool],
) -> List[FunctionToolParam]:
    """Convert tool specs to OpenAI Responses API function format, excluding computer tool."""
    result: List[FunctionToolParam] = []
    for tool in tools:
        # Skip computer tool as it's handled by computer_use_preview
        if getattr(tool, 'name', None) != 'computer':
            result.append(_spec_to_openai_responses_function(tool.internal_spec()))
    return result


def extract_display_from_computer_tool(params: dict) -> tuple[int, int]:
    """Extract display dimensions from computer tool parameters."""
    default_width = 1024
    default_height = 768

    # Look for computer tool in the tools list
    tools = params.get('tools', [])
    for tool in tools:
        if tool.get('name') == 'computer':
            input_schema = tool.get('input_schema', {})
            properties = input_schema.get('properties', {})

            # Try to extract display_width and display_height from the schema
            display_width_info = properties.get('display_width', {})
            display_height_info = properties.get('display_height', {})

            # Check for default values
            width = display_width_info.get('default', default_width)
            height = display_height_info.get('default', default_height)

            return width, height

    return default_width, default_height


def build_openai_preview_tool(
    display_size: tuple[int, int], environment: str = 'windows'
) -> ComputerToolParam:
    """Build the computer_use_preview tool for OpenAI Responses API."""
    width, height = display_size
    return cast(
        ComputerToolParam,
        {
            'type': 'computer_use_preview',
            'display_width': width,
            'display_height': height,
            'environment': environment,
        },
    )


def beta_messages_to_openai_responses_input(
    messages: list[BetaMessageParam],
) -> ResponseInputParam:
    """Convert Anthropic-format messages to OpenAI Responses API input format.

    The Responses API only accepts user input messages, so we need to consolidate
    the conversation history appropriately.
    """
    if not messages:
        return []

    # Take the most recent user message or create a summary
    response_messages = []

    # Find the most recent user message with actual content
    for msg in reversed(messages):
        if msg.get('role') == 'user':
            content = msg.get('content')

            # Handle string content
            if isinstance(content, str):
                response_messages.append(
                    {
                        'role': 'user',
                        'content': content,
                    }
                )
                break

            # Handle list content (blocks)
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                        elif block.get('type') == 'tool_result':
                            # Include tool results as context
                            if 'error' in block:
                                text_parts.append(f'[Tool Error: {block["error"]}]')
                            else:
                                # Extract text from tool result content
                                result_content = block.get('content', [])
                                for rc in result_content:
                                    if (
                                        isinstance(rc, dict)
                                        and rc.get('type') == 'text'
                                    ):
                                        text = rc.get('text', '')
                                        if text:
                                            text_parts.append(f'[Tool Result: {text}]')

                if text_parts:
                    response_messages.append(
                        {
                            'role': 'user',
                            'content': '\n'.join(text_parts),
                        }
                    )
                    break

    # If no user message found, create a default one
    if not response_messages:
        response_messages.append(
            {
                'role': 'user',
                'content': 'Please continue with the task.',
            }
        )

    return cast(ResponseInputParam, response_messages)


def responses_output_to_blocks(
    response: Response,
) -> tuple[list[BetaContentBlockParam], str]:
    """Convert OpenAI Responses API output to Anthropic-format blocks and stop reason."""
    content_blocks: list[BetaContentBlockParam] = []

    # Extract output from the response
    output = getattr(response, 'output', [])

    if not output:
        # No output, return empty blocks
        return content_blocks, 'end_turn'

    # Process each output item
    for item in output:
        if isinstance(item, dict):
            item_type = item.get('type')

            if item_type == 'text':
                # Text output
                content = item.get('content', '')
                if content:
                    content_blocks.append(BetaTextBlockParam(type='text', text=content))

            elif item_type == 'tool_use':
                # Tool use output - map to Anthropic format
                tool_name = item.get('name', 'computer')
                tool_input = item.get('input', {})
                tool_id = item.get('id', 'tool_use_' + str(len(content_blocks)))

                # For computer_use_preview, map to our computer tool format
                if tool_name == 'computer_use_preview':
                    tool_name = 'computer'
                    # The input should already be in the right format

                content_blocks.append(
                    BetaToolUseBlockParam(
                        type='tool_use',
                        id=tool_id,
                        name=tool_name,
                        input=tool_input,
                    )
                )

    # Determine stop reason
    finish_reason = getattr(response, 'finish_reason', 'stop')
    stop_reason_map = {
        'stop': 'end_turn',
        'tool_calls': 'tool_use',
        'tool_use': 'tool_use',
        'length': 'max_tokens',
        'max_tokens': 'max_tokens',
    }
    stop_reason = stop_reason_map.get(finish_reason, 'end_turn')

    return content_blocks, stop_reason
