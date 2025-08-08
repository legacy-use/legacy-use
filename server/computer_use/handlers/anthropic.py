"""
Anthropic provider handler implementation.

This handler manages all Anthropic-specific logic including Claude models
via direct API, Bedrock, and Vertex AI.
"""

from typing import Any, Optional

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
)

from server.computer_use.client import LegacyUseClient
from server.computer_use.config import APIProvider
from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools import ToolCollection, ToolResult
from server.computer_use.utils import (
    _inject_prompt_caching,
    _make_api_tool_result,
    _maybe_filter_to_n_most_recent_images,
    _response_to_params,
)
from server.settings import settings


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

    async def initialize_client(self, api_key: str, **kwargs) -> Any:
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
            aws_region = self.tenant_setting('AWS_REGION') or settings.AWS_REGION
            aws_access_key = (
                self.tenant_setting('AWS_ACCESS_KEY_ID') or settings.AWS_ACCESS_KEY_ID
            )
            aws_secret_key = (
                self.tenant_setting('AWS_SECRET_ACCESS_KEY')
                or settings.AWS_SECRET_ACCESS_KEY
            )
            aws_session_token = (
                self.tenant_setting('AWS_SESSION_TOKEN') or settings.AWS_SESSION_TOKEN
            )

            # Initialize with available credentials
            bedrock_kwargs = {'aws_region': aws_region}
            if aws_access_key and aws_secret_key:
                bedrock_kwargs['aws_access_key'] = aws_access_key
                bedrock_kwargs['aws_secret_key'] = aws_secret_key
                if aws_session_token:
                    bedrock_kwargs['aws_session_token'] = aws_session_token

            logger.info(f'Using AsyncAnthropicBedrock client with region: {aws_region}')
            return AsyncAnthropicBedrock(**bedrock_kwargs)

        elif self.provider == APIProvider.LEGACYUSE_PROXY:
            proxy_key = (
                self.tenant_setting('LEGACYUSE_PROXY_API_KEY')
                or settings.LEGACYUSE_PROXY_API_KEY
            )
            return LegacyUseClient(api_key=proxy_key)

        else:
            raise ValueError(f'Unsupported Anthropic provider: {self.provider}')

    def prepare_system(self, system_prompt: str) -> Any:
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
        # Apply prompt caching if enabled
        if self.enable_prompt_caching:
            _inject_prompt_caching(messages)

        # Filter images if configured
        if self.only_n_most_recent_images:
            _maybe_filter_to_n_most_recent_images(
                messages,
                self.only_n_most_recent_images,
                min_removal_threshold=self.image_truncation_threshold,
            )

        return messages

    def prepare_tools(self, tool_collection: ToolCollection) -> Any:
        """Convert tool collection to Anthropic format."""
        return tool_collection.to_params()

    def get_betas(self) -> list[str]:
        """Get list of beta flags including tool-specific ones."""
        betas = super().get_betas()
        if self.tool_beta_flag:
            betas.append(self.tool_beta_flag)
        return betas

    async def call_api(
        self,
        client: Any,
        messages: list[Any],
        system: Any,
        tools: Any,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[Any, httpx.Request, httpx.Response]:
        """Make API call to Anthropic."""
        betas = self.get_betas()

        # log the tools being sent to anthropic
        logger.info(f'Calling Anthropic API with model: {model}')
        logger.debug(
            f'Tools being sent to Anthropic: {[t["name"] for t in tools] if tools else "None"}'
        )
        logger.debug(f'Messages being sent to Anthropic: {messages}')
        logger.debug(f'System being sent to Anthropic: {system}')

        try:
            raw_response = await client.beta.messages.with_raw_response.create(
                max_tokens=max_tokens,
                messages=messages,
                model=model,
                system=[system],
                tools=tools,
                betas=betas,
                temperature=temperature,
            )

            parsed_response = raw_response.parse()
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
        self, response: Any
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Convert Anthropic response to content blocks and stop reason.
        Response is already in Anthropic format.
        """
        content_blocks = _response_to_params(response)
        stop_reason = response.stop_reason
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
        """Create tool result block using existing utility."""
        return _make_api_tool_result(result, tool_use_id)
