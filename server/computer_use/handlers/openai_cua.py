"""
OpenAI CUA (Computer-Using Agent) provider handler implementation.

This handler uses OpenAI's Responses API with the built-in `computer_use_preview` tool
and maps its output to our Anthropic-format content blocks and tool_use inputs
for execution by our existing `computer` tool.
"""

from typing import Optional

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
    beta_messages_to_openai_responses_input,
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
        Convert Anthropic-format messages to OpenAI Responses API `input` format:
        a list of objects with {role: 'user', content: [{type: input_text|input_image, ...}]}.
        """
        # Apply common preprocessing (prompt caching off for this handler; trim images to 1)
        self.preprocess_messages(messages, image_truncation_threshold=1)
        provider_messages: ResponseInputParam = beta_messages_to_openai_responses_input(
            messages
        )
        logger.info(
            f'Converted to {len(provider_messages)} OpenAI Responses input messages (CUA)'
        )
        return provider_messages

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
