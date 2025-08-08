"""
OpenAI provider handler implementation.

This handler demonstrates how to add support for a new provider (OpenAI)
by mapping between OpenAI's format and the Anthropic format used for DB storage.
"""

import json
from typing import Any, Optional

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection, ToolResult

from openai import AsyncOpenAI


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

    async def initialize_client(self, api_key: str, **kwargs) -> Any:
        """Initialize OpenAI client."""
        # Note: This would require installing openai package
        return AsyncOpenAI(api_key=api_key)

    def prepare_system(self, system_prompt: str) -> str:
        """
        Prepare system prompt for OpenAI.
        OpenAI uses a simple string for system prompts.
        """
        # Add OpenAI-specific instructions to the system prompt
        openai_instructions = """
CRITICAL TOOL USAGE RULES FOR THIS TASK:

1. ALWAYS START with computer(action="screenshot") to see the current screen state before any other action.

2. For the 'computer' tool:
   - First action MUST be: computer(action="screenshot")
   - To open Windows settings: computer(action="key", key="Super_L") then type "settings"
   - To click: computer(action="left_click", coordinate=[x, y])
   - To type text: computer(action="type", text="your text")
   - To press keys: computer(action="key", key="Return") or key="Tab", etc.

3. For the 'extraction' tool - use ONLY when you have found the requested information:
   - MUST pass: extraction(data={your_data})
   - Example: extraction(data={"time": "12:22"})

4. For 'ui_not_as_expected' tool - use when the UI doesn't match expectations:
   - Pass: ui_not_as_expected(reasoning="explanation of what went wrong")
   - Use this if a button doesn't exist, UI looks different, or actions fail

5. IMPORTANT: After EVERY computer action, the system will return a screenshot. Look at it before proceeding.

"""
        return openai_instructions + system_prompt

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[dict]:
        """
        Convert Anthropic-format messages to OpenAI format.

        OpenAI format:
        {
            "role": "user" | "assistant" | "system" | "tool",
            "content": str | list[content_parts],
            "tool_calls": [...] (for assistant messages with tools),
            "tool_call_id": str (for tool messages)
        }
        """
        # Apply image filtering if configured
        if self.only_n_most_recent_images:
            from server.computer_use.utils import _maybe_filter_to_n_most_recent_images

            _maybe_filter_to_n_most_recent_images(
                messages,
                self.only_n_most_recent_images,
                min_removal_threshold=1,
            )

        openai_messages = []

        logger.info(
            f'Converting {len(messages)} messages from Anthropic to OpenAI format'
        )
        for msg_idx, msg in enumerate(messages):
            role = msg['role']
            content = msg['content']
            logger.debug(
                f'  Message {msg_idx}: role={role}, content_type={type(content).__name__}'
            )

            if isinstance(content, str):
                # Simple text message
                openai_messages.append(
                    {
                        'role': role,
                        'content': content,
                    }
                )
            elif isinstance(content, list):
                # Complex message with multiple content blocks
                openai_msg = {'role': role}
                content_parts = []
                tool_calls = []

                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get('type')

                        if block_type == 'text':
                            content_parts.append(
                                {
                                    'type': 'text',
                                    'text': block.get('text', ''),
                                }
                            )

                        elif block_type == 'image':
                            # Convert image block
                            source = block.get('source', {})
                            if source.get('type') == 'base64':
                                content_parts.append(
                                    {
                                        'type': 'image_url',
                                        'image_url': {
                                            'url': f'data:{source.get("media_type", "image/png")};base64,{source.get("data", "")}',
                                        },
                                    }
                                )

                        elif block_type == 'tool_use':
                            # Convert tool use to OpenAI tool_calls
                            tool_calls.append(
                                {
                                    'id': block.get('id'),
                                    'type': 'function',
                                    'function': {
                                        'name': block.get('name'),
                                        'arguments': json.dumps(block.get('input', {})),
                                    },
                                }
                            )

                        elif block_type == 'tool_result':
                            # OpenAI handles tool results differently - they need special handling for images
                            tool_call_id = block.get('tool_use_id')

                            # Check if this is a screenshot result (has image content)
                            has_image = False
                            image_data = None
                            text_content = ''

                            if 'error' in block:
                                # Error case - simple text message
                                tool_msg = {
                                    'role': 'tool',
                                    'tool_call_id': tool_call_id,
                                    'content': block['error'],
                                }
                                openai_messages.append(tool_msg)
                            elif 'content' in block and isinstance(
                                block['content'], list
                            ):
                                # Process content items
                                for content_item in block['content']:
                                    if isinstance(content_item, dict):
                                        if content_item.get('type') == 'text':
                                            text_content = content_item.get('text', '')
                                        elif content_item.get('type') == 'image':
                                            has_image = True
                                            source = content_item.get('source', {})
                                            if source.get('type') == 'base64':
                                                image_data = source.get('data')

                                if has_image and image_data:
                                    # For screenshot results, we need to send the image as a user message
                                    # First send the tool result confirmation
                                    tool_msg = {
                                        'role': 'tool',
                                        'tool_call_id': tool_call_id,
                                        'content': text_content
                                        or 'Screenshot taken successfully',
                                    }
                                    openai_messages.append(tool_msg)

                                    # Then add a user message with the image
                                    image_msg = {
                                        'role': 'user',
                                        'content': [
                                            {
                                                'type': 'text',
                                                'text': 'Here is the screenshot result:',
                                            },
                                            {
                                                'type': 'image_url',
                                                'image_url': {
                                                    'url': f'data:image/png;base64,{image_data}'
                                                },
                                            },
                                        ],
                                    }
                                    openai_messages.append(image_msg)
                                else:
                                    # Text-only tool result
                                    tool_msg = {
                                        'role': 'tool',
                                        'tool_call_id': tool_call_id,
                                        'content': text_content
                                        or 'Tool executed successfully',
                                    }
                                    openai_messages.append(tool_msg)
                            else:
                                # No content - simple success message
                                tool_msg = {
                                    'role': 'tool',
                                    'tool_call_id': tool_call_id,
                                    'content': 'Tool executed successfully',
                                }
                                openai_messages.append(tool_msg)

                            continue  # Skip adding to current message

                # Add content and tool calls to message
                if content_parts:
                    openai_msg['content'] = (
                        content_parts
                        if len(content_parts) > 1
                        else content_parts[0]['text']
                    )
                if tool_calls:
                    openai_msg['tool_calls'] = tool_calls

                if 'content' in openai_msg or 'tool_calls' in openai_msg:
                    openai_messages.append(openai_msg)

        logger.info(f'Converted to {len(openai_messages)} OpenAI messages')
        logger.debug(f'Message types: {[m["role"] for m in openai_messages]}')

        return openai_messages

    def prepare_tools(self, tool_collection: ToolCollection) -> list[dict]:
        """Convert tool collection to OpenAI tools format using tool adapters."""
        tools = tool_collection.to_openai_tools()
        logger.debug(
            f'OpenAI tools after conversion: {[t["function"]["name"] for t in tools]}'
        )
        return tools

    async def call_api(
        self,
        client: Any,
        messages: list[Any],
        system: str,
        tools: list[dict],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[Any, httpx.Request, httpx.Response]:
        """Make API call to OpenAI."""
        # Add system message at the beginning if provided
        full_messages = []
        if system:
            full_messages.append({'role': 'system', 'content': system})
        full_messages.extend(messages)

        # Log the tools being sent to OpenAI for debugging
        logger.info('=== OpenAI API Call ===')
        logger.info(f'Model: {model}')
        logger.info(f'Messages: {len(full_messages)} total')
        logger.info(
            f'Tools: {[t["function"]["name"] for t in tools] if tools else "None"}'
        )
        logger.info(f'Tools: {tools}')
        logger.info(f'Tenant schema: {self.tenant_schema}')
        logger.debug(f'Max tokens: {max_tokens}, Temperature: {temperature}')
        # logger.debug(f'Full messages: {full_messages}')

        response = await client.chat.completions.with_raw_response.create(
            model=model,
            messages=full_messages,
            tools=tools if tools else None,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        parsed_response = response.parse()

        # Log response info
        logger.info('=== OpenAI API Response Received ===')
        if parsed_response.choices and parsed_response.choices[0].message.tool_calls:
            tool_calls = parsed_response.choices[0].message.tool_calls
            logger.info(f'Response contains {len(tool_calls)} tool calls:')
            for tc in tool_calls:
                logger.info(f'  - {tc.function.name} (id: {tc.id[:20]}...)')
                logger.debug(f'    Args: {tc.function.arguments[:100]}...')
        else:
            logger.info('Response contains text content (no tool calls)')
        logger.info('=====================================')

        return parsed_response, response.http_response.request, response.http_response

    def convert_from_provider_response(
        self, response: Any
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
                try:
                    # Parse the function arguments
                    tool_input = json.loads(tool_call.function.arguments)

                    # Log the raw tool input for debugging
                    logger.info(
                        f'Processing tool call: {tool_call.function.name} (id: {tool_call.id})'
                    )
                    logger.debug(f'Raw arguments: {tool_call.function.arguments}')

                    # Special handling for computer tool
                    if tool_call.function.name == 'computer':
                        # Convert coordinate list to tuple if present
                        if 'coordinate' in tool_input and isinstance(
                            tool_input['coordinate'], list
                        ):
                            tool_input['coordinate'] = tuple(tool_input['coordinate'])

                        # Map 'click' action to 'left_click' for compatibility
                        if tool_input.get('action') == 'click':
                            tool_input['action'] = 'left_click'

                    # Special handling for extraction tool
                    elif tool_call.function.name == 'extraction':
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
                        name=tool_call.function.name,
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

    def parse_tool_use(self, content_block: BetaContentBlockParam) -> Optional[dict]:
        """Parse tool use from content block."""
        if content_block.get('type') == 'tool_use':
            return {
                'name': content_block.get('name'),
                'id': content_block.get('id'),
                'input': content_block.get('input'),
            }
        return None

    def make_tool_result(
        self, result: ToolResult, tool_use_id: str
    ) -> BetaToolResultBlockParam:
        """
        Create tool result block in Anthropic format.

        This is the same format regardless of provider since we're storing
        everything in Anthropic format in the database.
        """
        # Check if this is an extraction tool result
        is_extraction = 'extraction' in tool_use_id

        content: list[BetaTextBlockParam | BetaImageBlockParam] = []

        if result.error:
            return {
                'type': 'tool_result',
                'tool_use_id': tool_use_id,
                'content': [],
                'error': self._maybe_prepend_system(result, result.error),
            }

        if result.output:
            # Special handling for extraction tool results
            if is_extraction:
                try:
                    # Parse and validate the JSON
                    json_data = json.loads(result.output)
                    logger.info(f'Valid JSON extraction data: {json_data}')

                    # Extract just the result field if present
                    if isinstance(json_data, dict) and 'result' in json_data:
                        result_data = json_data['result']
                        formatted_output = json.dumps(
                            result_data, indent=2, ensure_ascii=False
                        )
                    else:
                        formatted_output = json.dumps(
                            json_data, indent=2, ensure_ascii=False
                        )

                    content.append(
                        {
                            'type': 'text',
                            'text': self._maybe_prepend_system(
                                result, formatted_output
                            ),
                        }
                    )
                except json.JSONDecodeError as e:
                    logger.error(f'Invalid JSON in extraction tool output: {e}')
                    return {
                        'type': 'tool_result',
                        'tool_use_id': tool_use_id,
                        'content': [],
                        'error': f'Error: Invalid JSON in extraction tool output: {e}',
                    }
            else:
                # Standard handling for non-extraction tools
                content.append(
                    {
                        'type': 'text',
                        'text': self._maybe_prepend_system(result, result.output),
                    }
                )

        if result.base64_image:
            content.append(
                {
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': 'image/png',
                        'data': result.base64_image,
                    },
                }
            )

        if not content:
            content.append({'type': 'text', 'text': 'system: Tool returned no output.'})

        return {
            'type': 'tool_result',
            'tool_use_id': tool_use_id,
            'content': content,
        }

    def _maybe_prepend_system(self, result: ToolResult, text: str) -> str:
        """Prepend system message if present."""
        if result.system:
            return f'<system>{result.system}</system>\n{text}'
        return text
