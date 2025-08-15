"""
OpenAI CUA (Computer-Using Agent) provider handler implementation.

This handler uses OpenAI's Responses API with the built-in `computer_use_preview` tool
and maps its output to our Anthropic-format content blocks and tool_use inputs
for execution by our existing `computer` tool.
"""

from typing import Optional, Any, cast

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaToolResultBlockParam,
)

from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection, ToolResult
from server.computer_use.utils import (
    _make_api_tool_result,
    summarize_openai_responses_input,
    summarize_beta_blocks,
)
from server.computer_use.converters import (
    extract_display_from_computer_tool,
    build_openai_preview_tool,
    responses_output_to_blocks,
    internal_specs_to_openai_responses_functions,
)

from openai import AsyncOpenAI
from openai.types.responses import (
    ToolParam,
    ComputerToolParam,
    FunctionToolParam,
    ResponseInputParam,
    Response,
)


class OpenAICUAHandler(BaseProviderHandler):
    """
    Handler for OpenAI Responses API with `computer_use_preview` tool.
    """

    def __init__(
        self,
        model: str = 'computer-use-preview',
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,  # Will be ignored
        **kwargs,
    ):
        super().__init__(
            token_efficient_tools_beta=token_efficient_tools_beta,
            only_n_most_recent_images=1,  # computer-use-preview only supports 1 image
            enable_prompt_caching=False,
            **kwargs,
        )
        self.model = model

    async def initialize_client(self, api_key: str, **kwargs) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=api_key)

    def prepare_system(self, system_prompt: str) -> str:
        # TODO: Remove, and find solution on how openAI can keep track on state of current job
        openai_instructions = """
        Keep meta information in your summary about where you are in the step by step guide. Keep also information about relevant information you extracted.
        Feel free to include additional information in your summary. There is no need to be short or concise.
"""
        return system_prompt + '\n\n' + openai_instructions

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> ResponseInputParam:
        """
        Convert Anthropic-format messages to OpenAI Responses API `input` format.

        The Responses API only accepts user input messages, so we need to convert
        the conversation history into a format that preserves context while fitting
        the API constraints.
        """
        # Apply common preprocessing (prompt caching off for this handler; trim images to 1)
        self.preprocess_messages(messages, image_truncation_threshold=1)
        provider_messages: ResponseInputParam = (
            self._convert_messages_for_responses_api(messages)
        )
        logger.info(
            f'Converted to {len(provider_messages)} OpenAI Responses input messages (CUA)'
        )
        return provider_messages

    def _convert_messages_for_responses_api(
        self, messages: list[BetaMessageParam]
    ) -> ResponseInputParam:
        """
        Convert messages to OpenAI Responses API format.

        Since the Responses API only accepts user input messages, we use the simple
        converter that maintains essential conversation context.
        """
        # Use the existing converter from converters.py but with some preprocessing
        from server.computer_use.converters import (
            beta_messages_to_openai_responses_input,
        )

        # The existing converter handles the basics, but we can improve it by
        # pre-processing to consolidate related messages
        consolidated_messages = self._consolidate_messages(messages)

        # Now convert using the standard converter
        return beta_messages_to_openai_responses_input(consolidated_messages)

    def _consolidate_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[BetaMessageParam]:
        """
        Consolidate related messages to reduce fragmentation.

        Groups assistant messages with their corresponding tool results.
        """
        if not messages:
            return []

        consolidated = []
        i = 0

        while i < len(messages):
            msg = messages[i]
            role = msg.get('role')

            # For user messages, check if it's just tool results
            if role == 'user':
                content = msg.get('content')
                if isinstance(content, list):
                    # Check if this is purely tool results
                    has_only_tool_results = all(
                        isinstance(block, dict) and block.get('type') == 'tool_result'
                        for block in content
                    )

                    if has_only_tool_results and i > 0:
                        # This is a tool result following an assistant message
                        # Merge it with the previous message if it was an assistant message
                        prev_msg = consolidated[-1] if consolidated else None
                        if prev_msg and prev_msg.get('role') == 'assistant':
                            # Merge the tool result into the assistant message
                            prev_content = prev_msg.get('content', [])
                            if not isinstance(prev_content, list):
                                prev_content = (
                                    [
                                        cast(
                                            Any,
                                            {'type': 'text', 'text': str(prev_content)},
                                        )
                                    ]
                                    if prev_content
                                    else []
                                )
                            else:
                                # Make a copy to avoid modifying the original
                                prev_content = list(prev_content)

                            # Add tool results as text blocks in the assistant message
                            for block in content:
                                if (
                                    isinstance(block, dict)
                                    and block.get('type') == 'tool_result'
                                ):
                                    if 'error' in block:
                                        prev_content.append(
                                            cast(
                                                Any,
                                                {
                                                    'type': 'text',
                                                    'text': f'[Tool Error: {block["error"]}]',
                                                },
                                            )
                                        )
                                    else:
                                        # Extract result content
                                        result_content = block.get('content', [])
                                        for rc in result_content:
                                            if isinstance(rc, dict):
                                                if rc.get('type') == 'text':
                                                    text = rc.get('text', '')
                                                    if (
                                                        text
                                                        and text
                                                        != 'Tool executed successfully'
                                                    ):
                                                        prev_content.append(
                                                            cast(
                                                                Any,
                                                                {
                                                                    'type': 'text',
                                                                    'text': f'[Tool Result: {text}]',
                                                                },
                                                            )
                                                        )
                                                elif rc.get('type') == 'image':
                                                    # Keep image block - it will be handled by the converter
                                                    prev_content.append(cast(Any, rc))

                            # Update the previous message
                            consolidated[-1] = {**prev_msg, 'content': prev_content}
                            i += 1
                            continue

                # Regular user message
                consolidated.append(msg)
                i += 1

            else:
                # Assistant or system message
                consolidated.append(msg)
                i += 1

        return consolidated

    def prepare_tools(self, tool_collection: ToolCollection) -> list[ToolParam]:
        """Replace `computer` tool with `computer_use_preview` and keep other tools in OpenAI format.

        - Extract display settings from the Anthropic `computer` tool if present
        - Exclude the `computer` tool from the OpenAI tools list
        - Include `computer_use_preview` tool definition for the Responses API
        - Map all other tools from each tool's internal_spec()
        """
        display_width = 1024
        display_height = 768
        environment = 'windows'

        params = tool_collection.to_params()
        display_width, display_height = extract_display_from_computer_tool(params)
        preview_tool: ComputerToolParam = build_openai_preview_tool(
            (display_width, display_height), environment
        )
        # Build functions for non-computer tools from internal specs
        flattened_tools: list[FunctionToolParam] = (
            internal_specs_to_openai_responses_functions(list(tool_collection.tools))
        )
        tools_result: list[ToolParam] = [preview_tool, *flattened_tools]
        logger.debug(
            f'OpenAI CUA tools prepared: preview + '
            f'{[t.get("name") if t.get("type") == "function" else t.get("type") for t in flattened_tools]}'
        )
        return tools_result

    async def call_api(
        self,
        client: AsyncOpenAI,
        messages: ResponseInputParam,
        system: str,
        tools: list[ToolParam],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[Response, httpx.Request, httpx.Response]:
        logger.info('=== OpenAI CUA API Call ===')
        logger.info(f'Model: {model}, Max tokens: {max_tokens}, Temp: {temperature}')
        logger.info(f'Tenant schema: {self.tenant_schema}')
        logger.info(f'Input summary: {summarize_openai_responses_input(messages)}')
        logger.debug(f'Tools sent: {[t.get("type") for t in tools]}')

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
            return message

        logger.info(f'Conversation structure: {shorten_message(messages)}')

        response = await client.responses.with_raw_response.create(
            model=model,
            input=messages,
            tools=tools,
            reasoning={'summary': 'concise'},
            truncation='auto',
            instructions=system if system else None,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        parsed_response = response.parse()
        logger.info(
            f'Output summary: {summarize_beta_blocks(responses_output_to_blocks(parsed_response)[0])}'
        )

        return parsed_response, response.http_response.request, response.http_response

    def convert_from_provider_response(
        self, response: Response
    ) -> tuple[list[BetaContentBlockParam], str]:
        """Convert Responses API output to Anthropic blocks and stop reason."""
        logger.info(
            f'OpenAI Responses output items: {len(getattr(response, "output", []) or [])} (CUA preview mode)'
        )
        return responses_output_to_blocks(response)

    def make_tool_result(
        self, result: ToolResult, tool_use_id: str
    ) -> BetaToolResultBlockParam:
        return _make_api_tool_result(result, tool_use_id)
