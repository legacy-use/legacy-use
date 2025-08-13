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
)
from server.computer_use.handlers.converter_utils import (
    beta_messages_to_openai_responses_input,
    extract_display_from_computer_tool,
    build_openai_preview_tool,
    internal_specs_to_openai_responses_functions,
    responses_output_to_blocks,
)

from openai import AsyncOpenAI
from openai.types.responses import (
    ToolParam,
    ComputerToolParam,
    FunctionToolParam,
    ResponseInputParam,
    Response,
)
import instructor


class OpenAICUAHandler(BaseProviderHandler):
    """
    Handler for OpenAI Responses API with `computer_use_preview` tool.

    This handler is designed for OpenAI's computer-using agent models that support
    the Responses API with built-in computer interaction capabilities.
    """

    def __init__(
        self,
        model: str = 'computer-use-preview',
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,  # Will be ignored
        **kwargs,
    ):
        """
        Initialize the OpenAI CUA handler.

        Args:
            model: Model identifier for the computer-use-preview model
            token_efficient_tools_beta: Not used for this handler
            only_n_most_recent_images: Will be overridden to 1 (API limitation)
            **kwargs: Additional provider-specific parameters
        """
        super().__init__(
            token_efficient_tools_beta=token_efficient_tools_beta,
            only_n_most_recent_images=1,  # computer-use-preview only supports 1 image
            enable_prompt_caching=False,  # Not supported by Responses API
            **kwargs,
        )
        self.model = model

    async def initialize_client(
        self, api_key: str, **kwargs
    ) -> instructor.AsyncInstructor:
        """Initialize and return the OpenAI client."""
        # Check for tenant-specific API key first
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
        """Prepare system prompt for OpenAI Responses API."""
        # Add OpenAI-specific instructions for better state tracking
        openai_instructions = """

Keep meta information in your summary about where you are in the step by step guide. 
Keep also information about relevant information you extracted.
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
        processed_messages = self.preprocess_messages(
            messages, image_truncation_threshold=1
        )

        # Consolidate messages for better context preservation
        consolidated_messages = self._consolidate_messages(processed_messages)

        # Convert to Responses API format
        provider_messages = beta_messages_to_openai_responses_input(
            consolidated_messages
        )

        logger.info(
            f'Converted {len(messages)} messages to {len(provider_messages)} OpenAI Responses input messages (CUA)'
        )
        return provider_messages

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
        """
        Replace `computer` tool with `computer_use_preview` and keep other tools in OpenAI format.

        - Extract display settings from the Anthropic `computer` tool if present
        - Exclude the `computer` tool from the OpenAI tools list
        - Include `computer_use_preview` tool definition for the Responses API
        - Map all other tools from each tool's internal_spec()
        """
        # Default display settings
        display_width = 1024
        display_height = 768
        environment = 'windows'

        # Extract display dimensions from computer tool if present
        tool_list = tool_collection.to_params()
        # to_params() returns a list, we need to wrap it in a dict for extract_display_from_computer_tool
        tool_params = {'tools': tool_list}
        display_width, display_height = extract_display_from_computer_tool(tool_params)

        # Build the computer_use_preview tool
        preview_tool: ComputerToolParam = build_openai_preview_tool(
            (display_width, display_height), environment
        )

        # Build functions for non-computer tools from internal specs
        flattened_tools: list[FunctionToolParam] = (
            internal_specs_to_openai_responses_functions(list(tool_collection.tools))
        )

        # Combine all tools
        tools_result: list[ToolParam] = [preview_tool, *flattened_tools]

        logger.debug(
            f'OpenAI CUA tools prepared: computer_use_preview + '
            f'{[t.get("name") if t.get("type") == "function" else t.get("type") for t in flattened_tools]}'
        )
        return tools_result

    async def call_api(
        self,
        client: instructor.AsyncInstructor,
        messages: ResponseInputParam,
        system: str,
        tools: list[ToolParam],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[Response, httpx.Request, httpx.Response]:
        """
        Make API call to OpenAI Responses API.

        Args:
            client: The instructor.AsyncInstructor client instance
            messages: Messages in Responses API format
            system: System prompt (instructions)
            tools: Tools in Responses API format
            model: Model identifier
            max_tokens: Maximum output tokens
            temperature: Temperature for generation
            **kwargs: Additional parameters

        Returns:
            Tuple of (parsed response, request, raw response)
        """
        # Ensure we have the right client type
        if not isinstance(client, AsyncOpenAI):
            if hasattr(self, '_client') and self._client:
                client = self._client
            else:
                raise ValueError('OpenAI client not properly initialized')

        # Make the API call
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

        return parsed_response, response.http_response.request, response.http_response

    async def execute(
        self,
        client: Any,  # Will be AsyncOpenAI or instructor.AsyncInstructor
        messages: list[BetaMessageParam],
        system: str,
        tools: ToolCollection,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        """
        Execute the API call to OpenAI Responses API and return standardized response.

        This is the public interface that handles all conversions internally.

        Args:
            client: The client instance (will be ignored, we use our own)
            messages: Messages in Anthropic format
            system: System prompt
            tools: Tool collection
            model: Model identifier
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
            **kwargs: Additional parameters

        Returns:
            Tuple of (content_blocks, stop_reason, request, raw_response)
        """
        # Ensure we have an OpenAI client
        if not self._client:
            # Try to extract API key from client if it's an instructor client
            api_key = kwargs.get('api_key', '')
            self._client = await self.initialize_client(api_key)

        # Convert inputs to provider format
        provider_messages = self.convert_to_provider_messages(messages)
        system_str = self.prepare_system(system)
        provider_tools = self.prepare_tools(tools)

        # Make the API call
        parsed_response, request, raw_response = await self.call_api(
            client=self._client,
            messages=provider_messages,
            system=system_str,
            tools=provider_tools,
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
        """Create a tool result block in Anthropic format."""
        return _make_api_tool_result(result, tool_use_id)
