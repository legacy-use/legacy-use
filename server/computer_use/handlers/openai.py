"""
OpenAI provider handler implementation.

This handler demonstrates how to add support for a new provider (OpenAI)
by mapping between OpenAI's format and the Anthropic format used for DB storage.
"""

import json
from typing import Optional, cast

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection, ToolResult
from server.computer_use.utils import _make_api_tool_result
from server.computer_use.converters import (
    internal_specs_to_openai_chat_functions,
)

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
    ChatCompletion,
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionContentPartImageParam,
    ChatCompletionMessageToolCallParam,
)


class OpenAIHandler(BaseProviderHandler):
    """
    Handler for OpenAI API provider.

    This is an example implementation showing how to map between OpenAI's
    message format and the Anthropic format used for database storage.
    """

    def __init__(
        self,
        model: str = 'gpt-4o',
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize the OpenAI handler.

        Args:
            model: Model identifier (e.g., 'gpt-4o', 'gpt-4-turbo')
            token_efficient_tools_beta: Not used for OpenAI
            only_n_most_recent_images: Number of recent images to keep
            **kwargs: Additional provider-specific parameters
        """
        super().__init__(
            token_efficient_tools_beta=token_efficient_tools_beta,
            only_n_most_recent_images=only_n_most_recent_images,
            enable_prompt_caching=False,  # OpenAI doesn't support prompt caching
            **kwargs,
        )
        self.model = model
        # Keep this handler focused on Chat Completions + function calling

    async def initialize_client(self, api_key: str, **kwargs) -> AsyncOpenAI:
        """Initialize OpenAI client."""
        # Prefer tenant-specific key if available
        return AsyncOpenAI(api_key=api_key)

    def prepare_system(self, system_prompt: str) -> str:
        """
        Prepare system prompt for OpenAI.
        OpenAI uses a simple string for system prompts.
        """
        return system_prompt

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[ChatCompletionMessageParam]:
        """
        Convert Anthropic-format messages to OpenAI format.

        OpenAI format:
        {
            "role": "user" | "assistant" | "system" | "tool",
            "content": str | list[content_parts],
            "tool_calls": [...] (for assistant messages with tools),
            "tool_call_id": str (for tool messages)
        }

        IMPORTANT: OpenAI requires all tool messages to directly follow the assistant
        message with tool_calls, without any user messages in between.
        """
        # Apply image filtering if configured
        if self.only_n_most_recent_images:
            from server.computer_use.utils import _maybe_filter_to_n_most_recent_images

            _maybe_filter_to_n_most_recent_images(
                messages,
                self.only_n_most_recent_images,
                min_removal_threshold=1,
            )

        openai_messages: list[ChatCompletionMessageParam] = []

        logger.info(
            f'Converting {len(messages)} messages from Anthropic to OpenAI format'
        )

        msg_idx = 0
        while msg_idx < len(messages):
            msg = messages[msg_idx]
            role = msg['role']
            content = msg['content']
            logger.debug(
                f'  Message {msg_idx}: role={role}, content_type={type(content).__name__}'
            )

            if isinstance(content, str):
                # Simple text message
                if role == 'user':
                    user_msg: ChatCompletionUserMessageParam = {
                        'role': 'user',
                        'content': content,
                    }
                    openai_messages.append(user_msg)
                else:
                    assistant_msg: ChatCompletionAssistantMessageParam = {
                        'role': 'assistant',
                        'content': content,
                    }
                    openai_messages.append(assistant_msg)
                msg_idx += 1

            elif isinstance(content, list):
                # Check if this message contains tool results
                has_tool_results = any(
                    isinstance(block, dict) and block.get('type') == 'tool_result'
                    for block in content
                )

                if has_tool_results and role == 'user':
                    # This is a tool result message - collect all consecutive tool result messages
                    tool_messages: list[ChatCompletionToolMessageParam] = []
                    accumulated_images: list[
                        tuple[str, str]
                    ] = []  # (text, base64_data)

                    # Process this message and look ahead for more tool result messages
                    current_idx = msg_idx
                    while current_idx < len(messages):
                        current_msg = messages[current_idx]
                        current_role = current_msg['role']
                        current_content = current_msg['content']

                        # Only process user messages with tool_result blocks
                        if current_role != 'user' or not isinstance(
                            current_content, list
                        ):
                            break

                        has_tool_result = False
                        for block in current_content:
                            if (
                                isinstance(block, dict)
                                and block.get('type') == 'tool_result'
                            ):
                                has_tool_result = True
                                tool_call_id = block.get('tool_use_id')
                                text_content = ''
                                image_data = None

                                if 'error' in block:
                                    text_content = str(block['error'])
                                elif 'content' in block and isinstance(
                                    block['content'], list
                                ):
                                    for content_item in block['content']:
                                        if isinstance(content_item, dict):
                                            if content_item.get('type') == 'text':
                                                text_content = content_item.get(
                                                    'text', ''
                                                )
                                            elif content_item.get('type') == 'image':
                                                source = content_item.get('source', {})
                                                if source.get('type') == 'base64':
                                                    image_data = source.get('data')

                                # Create tool message
                                tool_msg: ChatCompletionToolMessageParam = {
                                    'role': 'tool',
                                    'tool_call_id': str(tool_call_id or 'tool_call'),
                                    'content': str(
                                        text_content or 'Tool executed successfully'
                                    ),
                                }
                                tool_messages.append(tool_msg)

                                # Accumulate image if present
                                if image_data:
                                    accumulated_images.append(
                                        (text_content, str(image_data))
                                    )

                        if not has_tool_result:
                            break
                        current_idx += 1

                    # Add all tool messages first
                    openai_messages.extend(tool_messages)

                    # Then add accumulated images as a single user message
                    if accumulated_images:
                        user_parts: list[ChatCompletionContentPartParam] = []
                        for text, img_data in accumulated_images:
                            if text:
                                user_parts.append(
                                    cast(
                                        ChatCompletionContentPartTextParam,
                                        {'type': 'text', 'text': text},
                                    )
                                )
                            user_parts.append(
                                cast(
                                    ChatCompletionContentPartImageParam,
                                    {
                                        'type': 'image_url',
                                        'image_url': {
                                            'url': f'data:image/png;base64,{img_data}'
                                        },
                                    },
                                )
                            )
                        image_msg: ChatCompletionUserMessageParam = {
                            'role': 'user',
                            'content': user_parts,
                        }
                        openai_messages.append(image_msg)

                    # Skip the messages we've processed
                    msg_idx = current_idx

                else:
                    # Not a tool result message - process normally
                    content_parts: list[ChatCompletionContentPartParam] = []
                    tool_calls: list[ChatCompletionMessageToolCallParam] = []

                    for block in content:
                        if isinstance(block, dict):
                            block_type = block.get('type')

                            if block_type == 'text':
                                content_parts.append(
                                    cast(
                                        ChatCompletionContentPartTextParam,
                                        {
                                            'type': 'text',
                                            'text': block.get('text', ''),
                                        },
                                    )
                                )

                            elif block_type == 'image':
                                source = block.get('source', {})
                                if source.get('type') == 'base64':
                                    content_parts.append(
                                        cast(
                                            ChatCompletionContentPartImageParam,
                                            {
                                                'type': 'image_url',
                                                'image_url': {
                                                    'url': f'data:{source.get("media_type", "image/png")};base64,{source.get("data", "")}',
                                                },
                                            },
                                        )
                                    )

                            elif block_type == 'tool_use':
                                tool_calls.append(
                                    cast(
                                        ChatCompletionMessageToolCallParam,
                                        {
                                            'id': str(block.get('id') or ''),
                                            'type': 'function',
                                            'function': {
                                                'name': str(block.get('name') or ''),
                                                'arguments': json.dumps(
                                                    block.get('input', {})
                                                ),
                                            },
                                        },
                                    )
                                )

                    # Add the message based on role
                    if role == 'user' and content_parts:
                        user_msg2: ChatCompletionUserMessageParam = {
                            'role': 'user',
                            'content': content_parts,
                        }
                        openai_messages.append(user_msg2)
                    elif role == 'assistant':
                        assistant_msg2: ChatCompletionAssistantMessageParam = {
                            'role': 'assistant',
                        }
                        if content_parts:
                            texts: list[str] = []
                            for part in content_parts:
                                if (
                                    isinstance(part, dict)
                                    and part.get('type') == 'text'
                                ):
                                    texts.append(str(part.get('text') or ''))
                            if texts:
                                assistant_msg2['content'] = '\n'.join(
                                    t for t in texts if t
                                )
                        if tool_calls:
                            assistant_msg2['tool_calls'] = tool_calls
                        openai_messages.append(assistant_msg2)

                    msg_idx += 1

        logger.info(f'Converted to {len(openai_messages)} OpenAI messages')
        logger.debug(f'Message types: {[m["role"] for m in openai_messages]}')

        return openai_messages

    def prepare_tools(
        self, tool_collection: ToolCollection
    ) -> list[ChatCompletionToolParam]:
        # Build OpenAI tool definitions from each tool's internal_spec().
        tools: list[ChatCompletionToolParam] = internal_specs_to_openai_chat_functions(
            list(tool_collection.tools)
        )
        logger.debug(
            f'OpenAI tools after conversion: {[t.get("function", {}).get("name") for t in tools]}'
        )
        return tools

    async def call_api(
        self,
        client: AsyncOpenAI,
        messages: list[ChatCompletionMessageParam],
        system: str,
        tools: list[ChatCompletionToolParam],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[ChatCompletion, httpx.Request, httpx.Response]:
        """Make API call to OpenAI."""
        logger.info('=== OpenAI API Call ===')
        logger.info(f'Model: {model}')
        logger.info(f'Tenant schema: {self.tenant_schema}')
        logger.debug(f'Max tokens: {max_tokens}, Temperature: {temperature}')

        # Chat Completions API with function tools
        # Add system message at the beginning if provided
        full_messages: list[ChatCompletionMessageParam] = []
        if system:
            sys_msg: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': system,
            }
            full_messages.append(sys_msg)
        full_messages.extend(messages)

        # iterate recursively and shorten any message longer than 10000 characters to 10
        def shorten_message(message):
            if isinstance(message, list):
                return [shorten_message(m) for m in message]
            elif isinstance(message, dict):
                return {
                    shorten_message(k): shorten_message(v) for k, v in message.items()
                }
            elif isinstance(message, str):
                if len(message) > 10000:
                    return message[:7] + '...'
                else:
                    return message
            return message

        logger.info(f'Messages: {shorten_message(full_messages)}')
        logger.info(
            f'Tools: {[t.get("function", {}).get("name") for t in tools] if tools else "None"}'
        )

        logger.info(f'Tools: {tools}')

        response = await client.chat.completions.with_raw_response.create(
            model=model,
            messages=full_messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        parsed_response = response.parse()
        logger.info(f'Parsed response: {parsed_response}')

        return parsed_response, response.http_response.request, response.http_response

    def convert_from_provider_response(
        self, response: ChatCompletion
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Convert OpenAI response to Anthropic format blocks and stop reason.

        Maps OpenAI's finish_reason to Anthropic's stop_reason:
        - 'stop' -> 'end_turn'
        - 'tool_calls' -> 'tool_use'
        - 'length' -> 'max_tokens'
        """
        content_blocks = []

        # Log the full response for debugging (Chat Completions path)
        logger.debug(f'Full OpenAI response object: {response}')

        # Extract message from OpenAI response
        message = response.choices[0].message
        logger.info(
            f'OpenAI message extracted - content: {message.content is not None}, tool_calls: {len(message.tool_calls) if message.tool_calls else 0}'
        )

        # Log tool calls if present
        if message.tool_calls:
            for tc in message.tool_calls:
                logger.info(f'OpenAI tool call: {tc.function.name} (id: {tc.id})')

        # Convert content
        if message.content:
            content_blocks.append(BetaTextBlockParam(type='text', text=message.content))

        # Helper: normalize key names for computer tool to match execution expectations
        def _normalize_key_combo(combo: str) -> str:
            if not isinstance(combo, str):
                return combo
            parts = [p.strip() for p in combo.replace(' ', '').split('+') if p.strip()]

            alias_map = {
                'esc': 'Escape',
                'escape': 'Escape',
                'enter': 'Return',
                'return': 'Return',
                'win': 'Super_L',
                'windows': 'Super_L',
                'super': 'Super_L',
                'meta': 'Super_L',
                'cmd': 'Super_L',
                'backspace': 'BackSpace',
                'del': 'Delete',
                'delete': 'Delete',
                'tab': 'Tab',
                'space': 'space',
                'pageup': 'Page_Up',
                'pagedown': 'Page_Down',
                'home': 'Home',
                'end': 'End',
                'up': 'Up',
                'down': 'Down',
                'left': 'Left',
                'right': 'Right',
                'printscreen': 'Print',
                'prtsc': 'Print',
            }

            def normalize_part(p: str) -> str:
                low = p.lower()
                # Collapse left/right variants to base modifiers
                if low in {'ctrl', 'control', 'ctrl_l', 'ctrl_r'}:
                    return 'ctrl'
                if low in {'shift', 'shift_l', 'shift_r'}:
                    return 'shift'
                if low in {'alt', 'alt_l', 'alt_r', 'option'}:
                    return 'alt'
                if low in {'super_l', 'super_r'}:
                    return 'Super_L'
                if low in alias_map:
                    return alias_map[low]
                # Function keys
                if low.startswith('f') and low[1:].isdigit():
                    return f'F{int(low[1:])}'
                # Single letters or digits: keep as-is
                if len(p) == 1:
                    return p
                # Title-case common words like 'Escape' already handled; otherwise keep original
                return p

            normalized = [normalize_part(p) for p in parts]
            return '+'.join(normalized)

        # Convert tool calls
        if message.tool_calls:
            logger.info(
                f'Converting {len(message.tool_calls)} tool calls from OpenAI response'
            )
            # Computer tool action names exposed as individual functions
            computer_actions = {
                'screenshot',
                'left_click',
                'mouse_move',
                'type',
                'key',
                'scroll',
                'left_click_drag',
                'right_click',
                'middle_click',
                'double_click',
                'triple_click',
                'left_mouse_down',
                'left_mouse_up',
                'hold_key',
                'wait',
            }

            for tool_call in message.tool_calls:
                try:
                    # Parse the function arguments
                    tool_input = json.loads(tool_call.function.arguments)

                    # Log the raw tool input for debugging
                    logger.info(
                        f'Processing tool call: {tool_call.function.name} (id: {tool_call.id})'
                    )
                    logger.debug(f'Raw arguments: {tool_call.function.arguments}')

                    tool_name = tool_call.function.name

                    # Special handling for computer tool or any of its action functions
                    if tool_name == 'computer' or tool_name in computer_actions:
                        # If called as an action function, embed action name
                        if tool_name in computer_actions:
                            tool_input = tool_input or {}
                            tool_input['action'] = tool_name

                        # Convert coordinate list to tuple if present
                        if 'coordinate' in tool_input and isinstance(
                            tool_input['coordinate'], list
                        ):
                            tool_input['coordinate'] = tuple(tool_input['coordinate'])

                        # Map legacy 'click' action to 'left_click' for compatibility
                        if tool_input.get('action') == 'click':
                            tool_input['action'] = 'left_click'

                        # Normalize key combos and key/text field for key-like actions
                        action = tool_input.get('action')
                        if action in {'key', 'hold_key', 'scroll'}:
                            if 'text' not in tool_input and 'key' in tool_input:
                                # Remap key -> text
                                tool_input['text'] = tool_input.pop('key')
                            # Normalize combo naming for xdotool compatibility
                            if 'text' in tool_input and isinstance(
                                tool_input['text'], str
                            ):
                                tool_input['text'] = _normalize_key_combo(
                                    tool_input['text']
                                )

                        # Always emit a single Anthropic tool_use for 'computer'
                        tool_use_block = BetaToolUseBlockParam(
                            type='tool_use',
                            id=tool_call.id,
                            name='computer',
                            input=tool_input,
                        )
                        content_blocks.append(tool_use_block)
                        logger.info(
                            f'Added computer tool_use from action {tool_name} - id: {tool_call.id}'
                        )

                        # Done with this tool call
                        continue

                    # Special handling for extraction tool
                    elif tool_name == 'extraction':
                        logger.info(
                            f'Processing extraction tool - original input: {tool_input}'
                        )

                        # OpenAI sends {name: ..., result: ...} directly based on our simplified schema
                        # But our extraction tool expects {data: {name: ..., result: ...}}
                        if 'data' not in tool_input:
                            # If 'data' field is missing but we have name and result, wrap them
                            if 'name' in tool_input and 'result' in tool_input:
                                original_input = tool_input.copy()
                                tool_input = {
                                    'data': {
                                        'name': tool_input['name'],
                                        'result': tool_input['result'],
                                    }
                                }
                                logger.info(
                                    f'Wrapped extraction data - from: {original_input} to: {tool_input}'
                                )
                            else:
                                logger.warning(
                                    f'Extraction tool call missing required fields. Has: {tool_input.keys()}, needs: name, result'
                                )
                        else:
                            # data field already exists, validate its structure
                            extraction_data = tool_input['data']
                            logger.info(
                                f"Extraction tool already has 'data' field: {extraction_data}"
                            )
                            if not isinstance(extraction_data, dict):
                                logger.warning(
                                    f'Extraction data is not a dict: {type(extraction_data)}'
                                )
                            elif (
                                'name' not in extraction_data
                                or 'result' not in extraction_data
                            ):
                                logger.warning(
                                    f'Extraction data missing required fields. Has: {extraction_data.keys()}, needs: name, result'
                                )

                    # Create the tool use block
                    tool_use_block = BetaToolUseBlockParam(
                        type='tool_use',
                        id=tool_call.id,
                        name=tool_name,
                        input=tool_input,
                    )
                    content_blocks.append(tool_use_block)

                    logger.info(
                        f'Added to content blocks - tool: {tool_call.function.name}, id: {tool_call.id}, input: {tool_input}'
                    )
                except json.JSONDecodeError as e:
                    logger.error(
                        f'Failed to parse tool arguments: {tool_call.function.arguments}, error: {e}'
                    )
                    # Add error block
                    content_blocks.append(
                        BetaTextBlockParam(
                            type='text',
                            text=f'Error parsing tool arguments for {tool_call.function.name}: {e}',
                        )
                    )

        # Map finish reason
        finish_reason = response.choices[0].finish_reason
        stop_reason_map = {
            'stop': 'end_turn',
            'tool_calls': 'tool_use',
            'length': 'max_tokens',
        }
        stop_reason = stop_reason_map.get(finish_reason, 'end_turn')

        # Final logging
        logger.info('=== OpenAI Response Conversion Complete ===')
        logger.info(f'Total content blocks created: {len(content_blocks)}')
        for i, block in enumerate(content_blocks):
            if block.get('type') == 'tool_use':
                logger.info(
                    f'  Block {i}: tool_use - {block.get("name")} (id: {block.get("id")})'
                )
            else:
                logger.info(f'  Block {i}: {block.get("type")}')
        logger.info(f'Stop reason: {stop_reason}')
        logger.info('==========================================')

        return content_blocks, stop_reason

    def make_tool_result(
        self, result: ToolResult, tool_use_id: str
    ) -> BetaToolResultBlockParam:
        """Create tool result block using existing utility to mirror Anthropic behavior."""
        return _make_api_tool_result(result, tool_use_id)
