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

    We build a single user message whose content contains:
    - input_text: the latest user instruction text
    - input_image: the latest screenshot image (if present)
    - input_text: brief context from the most recent tool_result text (if any)
    """
    if not messages:
        return []

    latest_image_data_url: str | None = None

    # Walk messages from newest to oldest to find:
    # - latest user instruction text
    # - most recent screenshot image (base64)
    for msg in reversed(messages):
        content = msg.get('content')

        # Capture latest image from any tool_result
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    # Build a tool_result content part for Responses API
                    block_content = block.get('content')
                    if isinstance(block_content, list):
                        for rc in block_content:
                            if (
                                isinstance(rc, dict)
                                and rc.get('type') == 'image'
                                and isinstance(rc.get('source'), dict)
                                and rc.get('source', {}).get('type') == 'base64'
                            ):
                                source = rc.get('source', {})
                                media_type = source.get('media_type', 'image/png')
                                data_b64 = source.get('data', '')
                                if isinstance(data_b64, str) and data_b64:
                                    latest_image_data_url = (
                                        f'data:{media_type};base64,{data_b64}'
                                    )
                                    break

                        # Ignore tool-result text here for CUA
                    block_content = block.get('content')
                    if not isinstance(block_content, list):
                        continue
                    for rc in block_content:
                        if (
                            isinstance(rc, dict)
                            and rc.get('type') == 'image'
                            and isinstance(rc.get('source'), dict)
                            and rc.get('source', {}).get('type') == 'base64'
                        ):
                            source = rc.get('source', {})
                            media_type = source.get('media_type', 'image/png')
                            data_b64 = source.get('data', '')
                            if isinstance(data_b64, str) and data_b64:
                                latest_image_data_url = (
                                    f'data:{media_type};base64,{data_b64}'
                                )
                                break
                    if latest_image_data_url:
                        break

    # Build content parts for Responses API - for CUA use image-only content
    content_parts: list[dict[str, Any]] = []

    if latest_image_data_url:
        # The Responses API expects image_url to be a string URL, not an object.
        content_parts.append(
            {'type': 'input_image', 'image_url': latest_image_data_url}
        )

    if not content_parts:
        content_parts.append({'type': 'input_text', 'text': 'Please continue.'})

    return cast(ResponseInputParam, [{'role': 'user', 'content': content_parts}])


def responses_output_to_blocks(
    response: Response,
) -> tuple[list[BetaContentBlockParam], str]:
    """Convert OpenAI Responses API output to Anthropic-format blocks and stop reason.

    Handles both dict-shaped items and typed SDK objects such as ResponseComputerToolCall.
    """
    content_blocks: list[BetaContentBlockParam] = []

    # Extract output from the response
    output = getattr(response, 'output', [])

    if not output:
        # No output, return empty blocks
        return content_blocks, 'end_turn'

    # Helper: convert a typed computer_call item into a tool_use block
    def _convert_computer_call_typed(item: Any) -> BetaToolUseBlockParam:
        # Use call_id so the next request can reference it via tool_result.tool_call_id
        tool_id = getattr(item, 'call_id', None) or getattr(
            item, 'id', f'tool_use_{len(content_blocks)}'
        )
        action = getattr(item, 'action', None)

        tool_input: dict[str, Any] = {}
        if action is not None:
            action_type = getattr(action, 'type', None) or getattr(
                action, 'action', None
            )
            if action_type:
                tool_input['action'] = str(action_type)

            # Attempt to extract common fields
            coord = getattr(action, 'coordinate', None)
            if coord is not None:
                x = getattr(coord, 'x', None)
                y = getattr(coord, 'y', None)
                if x is not None and y is not None:
                    tool_input['coordinate'] = (x, y)
                elif isinstance(coord, (list, tuple)) and len(coord) == 2:
                    tool_input['coordinate'] = (coord[0], coord[1])

            text_val = getattr(action, 'text', None)
            if text_val is not None:
                tool_input['text'] = text_val

            # Generic extraction of simple attributes
            for attr_name in (
                'button',
                'duration_ms',
                'scroll_amount',
                'direction',
                'modifiers',
            ):
                if hasattr(action, attr_name):
                    val = getattr(action, attr_name)
                    if val is not None and attr_name not in tool_input:
                        tool_input[attr_name] = val

        if 'action' not in tool_input:
            tool_input['action'] = 'screenshot'

        return BetaToolUseBlockParam(
            type='tool_use', id=str(tool_id), name='computer', input=tool_input
        )

    # Process each output item
    for item in output:
        if isinstance(item, dict):
            item_type = item.get('type')

            if item_type == 'text':
                content = item.get('content', '')
                if content:
                    content_blocks.append(BetaTextBlockParam(type='text', text=content))

            elif item_type in {'tool_use', 'computer_call'}:
                if item_type == 'computer_call':
                    content_blocks.append(_convert_computer_call_typed(item))
                else:
                    tool_name = item.get('name', 'computer')
                    tool_input = item.get('input', {})
                    tool_id = item.get('id', 'tool_use_' + str(len(content_blocks)))
                    if tool_name == 'computer_use_preview':
                        tool_name = 'computer'
                    content_blocks.append(
                        BetaToolUseBlockParam(
                            type='tool_use',
                            id=tool_id,
                            name=tool_name,
                            input=tool_input,
                        )
                    )
        else:
            # Likely a typed SDK object
            item_type = getattr(item, 'type', None)
            if item_type == 'computer_call':
                content_blocks.append(_convert_computer_call_typed(item))
            else:
                text = getattr(item, 'content', None) or getattr(item, 'text', None)
                if isinstance(text, str) and text:
                    content_blocks.append(BetaTextBlockParam(type='text', text=text))

    # Determine stop reason
    finish_reason = getattr(response, 'finish_reason', 'stop')
    stop_reason_map = {
        'stop': 'end_turn',
        'tool_calls': 'tool_use',
        'tool_use': 'tool_use',
        'length': 'max_tokens',
        'max_tokens': 'max_tokens',
        'completed': 'end_turn',
    }
    stop_reason = stop_reason_map.get(finish_reason, 'end_turn')

    return content_blocks, stop_reason
