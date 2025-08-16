"""
OpenAI provider handler implementation.

This handler manages all OpenAI-specific logic and mapping between OpenAI's format
and the Anthropic format used for DB storage.
"""

import json
from typing import Optional, cast

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)
import instructor

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection
from server.computer_use.handlers.converter_utils import (
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
    """

    # Computer tool action names exposed as individual functions
    COMPUTER_ACTIONS = {
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

    # Key normalization mappings for computer tool
    KEY_ALIASES = {
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

    # Modifier key normalization
    MODIFIER_KEYS = {
        'ctrl': {'ctrl', 'control', 'ctrl_l', 'ctrl_r'},
        'shift': {'shift', 'shift_l', 'shift_r'},
        'alt': {'alt', 'alt_l', 'alt_r', 'option'},
        'Super_L': {'super_l', 'super_r'},
    }

    # OpenAI finish reason to Anthropic stop reason mapping
    STOP_REASON_MAP = {
        'stop': 'end_turn',
        'tool_calls': 'tool_use',
        'length': 'max_tokens',
    }

    def __init__(
        self,
        model: str,
        tenant_schema: str,
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
            tenant_schema=tenant_schema,
            only_n_most_recent_images=only_n_most_recent_images,
            **kwargs,
        )
        self.model = model

    async def initialize_client(
        self, api_key: str, **kwargs
    ) -> instructor.AsyncInstructor:
        """Initialize OpenAI client."""
        tenant_key = self.tenant_setting('OPENAI_API_KEY')
        final_api_key = tenant_key or api_key
        if not final_api_key:
            raise ValueError(
                'OpenAI API key is required. Please provide either '
                'OPENAI_API_KEY tenant setting or api_key parameter.'
            )
        openai_client = AsyncOpenAI(api_key=final_api_key)
        return instructor.from_openai(openai_client, max_retries=self.max_retries)

    def prepare_system(self, system_prompt: str) -> str:
        """
        Prepare system prompt for OpenAI.
        """
        return system_prompt

    def _normalize_key_combo(self, combo: str) -> str:
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
        normalized = [self._normalize_key_part(p) for p in parts]
        return '+'.join(normalized)

    def _normalize_key_part(self, part: str) -> str:
        """
        Normalize a single key part.

        Args:
            part: Single key part to normalize

        Returns:
            Normalized key string
        """
        low = part.lower()

        # Check modifier keys
        for normalized, variants in self.MODIFIER_KEYS.items():
            if low in variants:
                return normalized

        # Check key aliases
        if low in self.KEY_ALIASES:
            return self.KEY_ALIASES[low]

        # Function keys
        if low.startswith('f') and low[1:].isdigit():
            return f'F{int(low[1:])}'

        # Single letters or digits: keep as-is
        if len(part) == 1:
            return part

        return part

    def _create_text_message(
        self, role: str, content: str
    ) -> ChatCompletionMessageParam:
        """
        Create a simple text message in OpenAI format.

        Args:
            role: Message role ('user' or 'assistant')
            content: Text content

        Returns:
            OpenAI message parameter
        """
        if role == 'user':
            return {
                'role': 'user',
                'content': content,
            }
        else:
            return {
                'role': 'assistant',
                'content': content,
            }

    def _process_tool_result_block(self, block: dict) -> tuple[str, str, Optional[str]]:
        """
        Process a single tool result block.

        Args:
            block: Tool result block from Anthropic format

        Returns:
            Tuple of (tool_call_id, text_content, image_data or None)
        """
        tool_call_id = block.get('tool_use_id')
        text_content = ''
        image_data = None

        if 'error' in block:
            text_content = str(block['error'])
        elif 'content' in block and isinstance(block['content'], list):
            for content_item in block['content']:
                if isinstance(content_item, dict):
                    if content_item.get('type') == 'text':
                        text_content = content_item.get('text', '')
                    elif content_item.get('type') == 'image':
                        source = content_item.get('source', {})
                        if source.get('type') == 'base64':
                            image_data = source.get('data')

        return str(tool_call_id or 'tool_call'), text_content, image_data

    def _create_tool_message(
        self, tool_call_id: str, content: str
    ) -> ChatCompletionToolMessageParam:
        """
        Create a tool message in OpenAI format.

        Args:
            tool_call_id: ID of the tool call
            content: Tool result content

        Returns:
            OpenAI tool message parameter
        """
        return {
            'role': 'tool',
            'tool_call_id': tool_call_id,
            'content': str(content or 'Tool executed successfully'),
        }

    def _create_image_message(
        self, images: list[tuple[str, str]]
    ) -> ChatCompletionUserMessageParam:
        """
        Create a user message with images.

        Args:
            images: List of (text, base64_data) tuples

        Returns:
            OpenAI user message with image content
        """
        user_parts: list[ChatCompletionContentPartParam] = []

        for text, img_data in images:
            if text:
                user_parts.append({'type': 'text', 'text': text})
            user_parts.append(
                {
                    'type': 'image_url',
                    'image_url': {'url': f'data:image/png;base64,{img_data}'},
                }
            )

        return {
            'role': 'user',
            'content': user_parts,
        }

    def _convert_content_block(
        self, block: dict
    ) -> tuple[
        Optional[ChatCompletionContentPartParam],
        Optional[ChatCompletionMessageToolCallParam],
    ]:
        """
        Convert a single content block to OpenAI format.

        Args:
            block: Content block in Anthropic format

        Returns:
            Tuple of (content_part or None, tool_call or None)
        """
        block_type = block.get('type')

        if block_type == 'text':
            content_part = cast(
                ChatCompletionContentPartTextParam,
                {
                    'type': 'text',
                    'text': block.get('text', ''),
                },
            )
            return content_part, None

        elif block_type == 'image':
            source = block.get('source', {})
            if source.get('type') == 'base64':
                content_part = cast(
                    ChatCompletionContentPartImageParam,
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:{source.get("media_type", "image/png")};base64,{source.get("data", "")}',
                        },
                    },
                )
                return content_part, None

        elif block_type == 'tool_use':
            tool_call = cast(
                ChatCompletionMessageToolCallParam,
                {
                    'id': str(block.get('id') or ''),
                    'type': 'function',
                    'function': {
                        'name': str(block.get('name') or ''),
                        'arguments': json.dumps(block.get('input', {})),
                    },
                },
            )
            return None, tool_call

        return None, None

    def _process_tool_result_messages(
        self, messages: list[BetaMessageParam], start_idx: int
    ) -> tuple[list[ChatCompletionMessageParam], int]:
        """
        Process consecutive tool result messages.

        Args:
            messages: List of all messages
            start_idx: Starting index for processing

        Returns:
            Tuple of (OpenAI messages list, next index to process)
        """
        tool_messages: list[ChatCompletionToolMessageParam] = []
        accumulated_images: list[tuple[str, str]] = []

        current_idx = start_idx
        while current_idx < len(messages):
            current_msg = messages[current_idx]
            current_role = current_msg['role']
            current_content = current_msg['content']

            # Only process user messages with tool_result blocks
            if current_role != 'user' or not isinstance(current_content, list):
                break

            has_tool_result = False
            for block in current_content:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    has_tool_result = True
                    # Cast to dict for type checker
                    block_dict = cast(dict, block)
                    tool_call_id, text_content, image_data = (
                        self._process_tool_result_block(block_dict)
                    )

                    # Create tool message
                    tool_messages.append(
                        self._create_tool_message(tool_call_id, text_content)
                    )

                    # Accumulate image if present
                    if image_data:
                        accumulated_images.append((text_content, str(image_data)))

            if not has_tool_result:
                break
            current_idx += 1

        # Combine results
        result_messages: list[ChatCompletionMessageParam] = []
        result_messages.extend(tool_messages)

        # Add accumulated images as a single user message
        if accumulated_images:
            result_messages.append(self._create_image_message(accumulated_images))

        return result_messages, current_idx

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
        # Apply common preprocessing
        messages = self.preprocess_messages(messages, image_truncation_threshold=1)
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
                openai_messages.append(self._create_text_message(role, content))
                msg_idx += 1

            elif isinstance(content, list):
                # Check if this message contains tool results
                has_tool_results = any(
                    isinstance(block, dict) and block.get('type') == 'tool_result'
                    for block in content
                )

                if has_tool_results and role == 'user':
                    # Process tool result messages
                    tool_messages, msg_idx = self._process_tool_result_messages(
                        messages, msg_idx
                    )
                    openai_messages.extend(tool_messages)
                else:
                    # Process regular content blocks
                    content_parts: list[ChatCompletionContentPartParam] = []
                    tool_calls: list[ChatCompletionMessageToolCallParam] = []

                    for block in content:
                        if isinstance(block, dict):
                            # Cast to dict for type checker
                            block_dict = cast(dict, block)
                            content_part, tool_call = self._convert_content_block(
                                block_dict
                            )
                            if content_part:
                                content_parts.append(content_part)
                            if tool_call:
                                tool_calls.append(tool_call)

                    # Create appropriate message based on role and content
                    if role == 'user' and content_parts:
                        openai_messages.append(
                            {
                                'role': 'user',
                                'content': content_parts,
                            }
                        )
                    elif role == 'assistant':
                        assistant_msg: ChatCompletionAssistantMessageParam = {
                            'role': 'assistant',
                        }

                        # Extract text content if any
                        if content_parts:
                            texts = [
                                str(part.get('text') or '')
                                for part in content_parts
                                if isinstance(part, dict) and part.get('type') == 'text'
                            ]
                            if texts:
                                assistant_msg['content'] = '\n'.join(
                                    t for t in texts if t
                                )

                        # Add tool calls if any
                        if tool_calls:
                            assistant_msg['tool_calls'] = tool_calls

                        openai_messages.append(assistant_msg)

                    msg_idx += 1

        logger.info(f'Converted to {len(openai_messages)} OpenAI messages')
        logger.debug(f'Message types: {[m["role"] for m in openai_messages]}')

        return openai_messages

    def prepare_tools(
        self, tool_collection: ToolCollection
    ) -> list[ChatCompletionToolParam]:
        """Convert tool collection to OpenAI format."""
        # Build OpenAI tool definitions from each tool's internal_spec().
        tools: list[ChatCompletionToolParam] = internal_specs_to_openai_chat_functions(
            list(tool_collection.tools)
        )
        logger.debug(
            f'OpenAI tools after conversion: {[t.get("function", {}).get("name") for t in tools]}'
        )
        return tools

    async def make_ai_request(
        self,
        client: instructor.AsyncInstructor,
        messages: list[ChatCompletionMessageParam],
        system: str,
        tools: list[ChatCompletionToolParam],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> tuple[ChatCompletion, httpx.Request, httpx.Response]:
        """Make raw API call to OpenAI and return provider-specific response."""
        # Build full message list with system message
        full_messages: list[ChatCompletionMessageParam] = []
        if system:
            sys_msg: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': system,
            }
            full_messages.append(sys_msg)
        full_messages.extend(messages)

        # Log debug information
        logger.info(f'Messages: {self._truncate_for_debug(full_messages)}')

        # Make API call
        response = await client.beta.chat.completions.with_raw_response.create(
            model=model,
            messages=full_messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        parsed_response = response.parse()
        logger.info(f'Parsed response: {parsed_response}')

        return (
            parsed_response,
            response.http_response.request,
            response.http_response,
        )

    async def execute(
        self,
        client: instructor.AsyncInstructor,
        messages: list[BetaMessageParam],
        system: str,
        tools: ToolCollection,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        """Make API call to OpenAI and return standardized response format."""
        # Convert inputs to provider format
        openai_messages = self.convert_to_provider_messages(messages)
        system_str = self.prepare_system(system)
        openai_tools = self.prepare_tools(tools)

        parsed_response, request, raw_response = await self.make_ai_request(
            client=client,
            messages=openai_messages,
            system=system_str,
            tools=openai_tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        # Convert response to standardized format
        content_blocks, stop_reason = self.convert_from_provider_response(
            parsed_response
        )

        return content_blocks, stop_reason, request, raw_response

    def _process_computer_tool(self, tool_name: str, tool_input: dict) -> dict:
        """
        Process computer tool input, normalizing action names and parameters.

        Args:
            tool_name: Name of the tool being called
            tool_input: Raw tool input

        Returns:
            Processed tool input
        """
        # If called as an action function, embed action name
        if tool_name in self.COMPUTER_ACTIONS:
            tool_input = tool_input or {}
            tool_input['action'] = tool_name

        # Convert coordinate list to tuple if present
        if 'coordinate' in tool_input and isinstance(tool_input['coordinate'], list):
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
            if 'text' in tool_input and isinstance(tool_input['text'], str):
                tool_input['text'] = self._normalize_key_combo(tool_input['text'])

        return tool_input

    def _process_extraction_tool(self, tool_input: dict) -> dict:
        """
        Process extraction tool input, ensuring proper data structure.

        Args:
            tool_input: Raw tool input

        Returns:
            Processed tool input with proper data structure
        """
        logger.info(f'Processing extraction tool - original input: {tool_input}')

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
            logger.info(f"Extraction tool already has 'data' field: {extraction_data}")
            if not isinstance(extraction_data, dict):
                logger.warning(
                    f'Extraction data is not a dict: {type(extraction_data)}'
                )
            elif 'name' not in extraction_data or 'result' not in extraction_data:
                logger.warning(
                    f'Extraction data missing required fields. Has: {extraction_data.keys()}, needs: name, result'
                )

        return tool_input

    def _convert_tool_call(self, tool_call) -> BetaContentBlockParam:
        """
        Convert a single OpenAI tool call to Anthropic format.

        Args:
            tool_call: OpenAI tool call object

        Returns:
            Anthropic tool use block
        """
        try:
            # Parse the function arguments
            tool_input = json.loads(tool_call.function.arguments)
            tool_name = tool_call.function.name

            # Log the raw tool input for debugging
            logger.info(f'Processing tool call: {tool_name} (id: {tool_call.id})')
            logger.debug(f'Raw arguments: {tool_call.function.arguments}')

            # Special handling for computer tool or any of its action functions
            if tool_name == 'computer' or tool_name in self.COMPUTER_ACTIONS:
                tool_input = self._process_computer_tool(tool_name, tool_input)
                # Always emit a single Anthropic tool_use for 'computer'
                tool_name = 'computer'
                logger.info(
                    f'Added computer tool_use from action {tool_call.function.name} - id: {tool_call.id}'
                )

            # Special handling for extraction tool
            elif tool_name == 'extraction':
                tool_input = self._process_extraction_tool(tool_input)

            # Create the tool use block
            return BetaToolUseBlockParam(
                type='tool_use',
                id=tool_call.id,
                name=tool_name,
                input=tool_input,
            )

        except json.JSONDecodeError as e:
            logger.error(
                f'Failed to parse tool arguments: {tool_call.function.arguments}, error: {e}'
            )
            # Return error as text block
            return BetaTextBlockParam(
                type='text',
                text=f'Error parsing tool arguments for {tool_call.function.name}: {e}',
            )

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

        # Log the full response for debugging
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

        # Convert tool calls
        if message.tool_calls:
            logger.info(
                f'Converting {len(message.tool_calls)} tool calls from OpenAI response'
            )
            for tool_call in message.tool_calls:
                block = self._convert_tool_call(tool_call)
                content_blocks.append(block)
                logger.info(
                    f'Added to content blocks - tool: {tool_call.function.name}, id: {tool_call.id}'
                )

        # Map finish reason
        finish_reason = response.choices[0].finish_reason
        stop_reason = self.STOP_REASON_MAP.get(finish_reason, 'end_turn')

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
