"""
Anthropic provider handler implementation.

This handler manages all Anthropic-specific logic including Claude models
via direct API, Bedrock, and Vertex AI.
"""

from typing import Optional, cast

import httpx
from anthropic import (
    APIError,
    APIResponseValidationError,
    APIStatusError,
    AsyncAnthropic,
    AsyncAnthropicBedrock,
    AsyncAnthropicVertex,
)
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUnionParam,
    BetaMessage,
)

from server.computer_use.client import LegacyUseClient
from server.computer_use.config import APIProvider
from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection, ToolResult
from server.computer_use.utils import (
    _make_api_tool_result,
    _response_to_params,
    summarize_beta_messages,
    summarize_beta_blocks,
)
from server.settings import settings


type AnthropicClient = (
    AsyncAnthropic | AsyncAnthropicBedrock | AsyncAnthropicVertex | LegacyUseClient
)


class AnthropicHandler(BaseProviderHandler):
    """Handler for Anthropic API providers (direct, Bedrock, Vertex)."""

    def __init__(
        self,
        provider: APIProvider,
        model: str,
        tool_beta_flag: Optional[str] = None,
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,
        tenant_schema: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the Anthropic handler.

        Args:
            provider: The specific Anthropic provider variant
            model: Model identifier
            tool_beta_flag: Tool-specific beta flag
            token_efficient_tools_beta: Whether to use token-efficient tools
            only_n_most_recent_images: Number of recent images to keep
            **kwargs: Additional provider-specific parameters
        """
        # Enable prompt caching for direct Anthropic API
        enable_prompt_caching = provider == APIProvider.ANTHROPIC

        super().__init__(
            token_efficient_tools_beta=token_efficient_tools_beta,
            only_n_most_recent_images=only_n_most_recent_images,
            enable_prompt_caching=enable_prompt_caching,
            tenant_schema=tenant_schema,
            **kwargs,
        )

        self.provider = provider
        self.model = model
        self.tool_beta_flag = tool_beta_flag
        self.image_truncation_threshold = 1

    async def initialize_client(self, api_key: str, **kwargs) -> AnthropicClient:
        """Initialize the appropriate Anthropic client based on provider."""
        # Reload settings to get latest environment variables
        settings.__init__()

        if self.provider == APIProvider.ANTHROPIC:
            # Prefer tenant-specific key if available
            tenant_key = self.tenant_setting('ANTHROPIC_API_KEY')
            return AsyncAnthropic(api_key=tenant_key or api_key, max_retries=4)

        elif self.provider == APIProvider.VERTEX:
            return AsyncAnthropicVertex()

        elif self.provider == APIProvider.BEDROCK:
            # AWS credentials from tenant settings (fallback to env settings)
            aws_region = self.tenant_setting('AWS_REGION') or getattr(
                settings, 'AWS_REGION', None
            )
            aws_access_key = self.tenant_setting('AWS_ACCESS_KEY_ID') or getattr(
                settings, 'AWS_ACCESS_KEY_ID', None
            )
            aws_secret_key = self.tenant_setting('AWS_SECRET_ACCESS_KEY') or getattr(
                settings, 'AWS_SECRET_ACCESS_KEY', None
            )
            aws_session_token = self.tenant_setting('AWS_SESSION_TOKEN') or getattr(
                settings, 'AWS_SESSION_TOKEN', None
            )

            # Initialize with available credentials using explicit kwargs for clearer typing
            logger.info(f'Using AsyncAnthropicBedrock client with region: {aws_region}')
            return AsyncAnthropicBedrock(
                aws_region=aws_region or '',
                aws_access_key=aws_access_key or None,
                aws_secret_key=aws_secret_key or None,
                aws_session_token=aws_session_token or None,
            )

        elif self.provider == APIProvider.LEGACYUSE_PROXY:
            proxy_key = (
                self.tenant_setting('LEGACYUSE_PROXY_API_KEY')
                or getattr(settings, 'LEGACYUSE_PROXY_API_KEY', None)
                or ''
            )
            return LegacyUseClient(api_key=proxy_key)

        else:
            raise ValueError(f'Unsupported Anthropic provider: {self.provider}')

    def prepare_system(self, system_prompt: str) -> BetaTextBlockParam:
        """Prepare system prompt as Anthropic BetaTextBlockParam."""
        system = BetaTextBlockParam(type='text', text=system_prompt)

        # Add cache control for prompt caching
        if self.enable_prompt_caching:
            system['cache_control'] = {'type': 'ephemeral'}

        return system

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[BetaMessageParam]:
        """
        For Anthropic, messages are already in the correct format.
        Apply caching and image filtering if configured.
        """
        # Apply common preprocessing (prompt caching + image filtering)
        return self.preprocess_messages(
            messages, image_truncation_threshold=self.image_truncation_threshold
        )

    def prepare_tools(
        self, tool_collection: ToolCollection
    ) -> list[BetaToolUnionParam]:
        """Convert tool collection to Anthropic format."""
        logger.info(f'tool_collection: {tool_collection}')
        return tool_collection.to_params()

    def get_betas(self) -> list[str]:
        """Get list of beta flags including tool-specific ones."""
        betas = super().get_betas()
        if self.tool_beta_flag:
            betas.append(self.tool_beta_flag)
        return betas

    async def call_api(
        self,
        client: AnthropicClient,
        messages: list[BetaMessageParam],
        system: BetaTextBlockParam,
        tools: list[BetaToolUnionParam],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[BetaMessage, httpx.Request, httpx.Response]:
        """Make API call to Anthropic."""
        betas = self.get_betas()

        # log the tools being sent to anthropic
        logger.info(f'Calling Anthropic API with model: {model}')
        logger.debug(
            f'Tools being sent to Anthropic: {[t["name"] for t in tools] if tools else "None"}'
        )
        logger.info(f'Tools: {tools}')
        logger.info(f'Tenant schema: {self.tenant_schema}')
        logger.info(f'Input summary: {summarize_beta_messages(messages)}')
        logger.debug('System being sent to Anthropic (text only)')

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

        logger.info(f'Shortened messages: {shorten_message(messages)}')

        try:
            # Some client variants expect `system` as str; extract from BetaTextBlockParam
            system_text = (
                system.get('text') if isinstance(system, dict) else str(system)
            )
            raw_response = await client.beta.messages.with_raw_response.create(
                max_tokens=max_tokens,
                messages=messages,
                model=model,
                system=system_text,
                tools=tools,
                betas=betas,
                temperature=temperature,
            )

            parsed_response = cast(BetaMessage, raw_response.parse())
            blocks = _response_to_params(parsed_response)
            logger.info(f'Output summary: {summarize_beta_blocks(blocks)}')
            return (
                parsed_response,
                raw_response.http_response.request,
                raw_response.http_response,
            )

        except (APIStatusError, APIResponseValidationError) as e:
            # Re-raise with original exception for proper error handling
            raise e
        except APIError as e:
            # Re-raise with original exception for proper error handling
            raise e

    def convert_from_provider_response(
        self, response: BetaMessage
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Convert Anthropic response to content blocks and stop reason.
        Response is already in Anthropic format.
        """
        content_blocks = _response_to_params(response)
        stop_reason = response.stop_reason or 'end_turn'
        return content_blocks, stop_reason

    def make_tool_result(
        self, result: ToolResult, tool_use_id: str
    ) -> BetaToolResultBlockParam:
        """Create tool result block using existing utility."""
        return _make_api_tool_result(result, tool_use_id)
