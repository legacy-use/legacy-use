"""
Anthropic provider handler implementation.

This handler manages all Anthropic-specific logic including Claude models
via direct API, Bedrock, and Vertex AI.
"""

from typing import Iterable, Optional, cast

import httpx
import instructor
from anthropic import (
    AsyncAnthropic,
    AsyncAnthropicBedrock,
    AsyncAnthropicVertex,
)
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolUnionParam,
)

from server.computer_use.client import LegacyUseClient
from server.computer_use.config import PROMPT_CACHING_BETA_FLAG, APIProvider
from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.tools.collection import ToolCollection
from server.settings import settings

from .message_converter import inject_prompt_caching
from .response_converter import convert_from_provider_response

AnthropicClient = (
    AsyncAnthropic | AsyncAnthropicBedrock | AsyncAnthropicVertex | LegacyUseClient
)


class AnthropicHandler(BaseProviderHandler):
    """Handler for Anthropic API providers (direct, Bedrock, Vertex)."""

    def __init__(
        self,
        provider: APIProvider,
        model: str,
        tenant_schema: str,
        tool_beta_flag: Optional[str] = None,
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,
        max_retries: int = 2,
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
        super().__init__(
            only_n_most_recent_images=only_n_most_recent_images,
            tenant_schema=tenant_schema,
            max_retries=max_retries,
            **kwargs,
        )

        self.provider = provider
        self.model = model
        self.tool_beta_flag = tool_beta_flag
        self.image_truncation_threshold = 1
        self.enable_prompt_caching = provider == APIProvider.ANTHROPIC
        self.token_efficient_tools_beta = token_efficient_tools_beta

    async def initialize_client(
        self, api_key: str, **kwargs
    ) -> instructor.AsyncInstructor:
        """Initialize the appropriate Anthropic client based on provider."""
        # Reload settings to get latest environment variables
        settings.__init__()

        client = None

        if self.provider == APIProvider.ANTHROPIC:
            # Prefer tenant-specific key if available
            tenant_key = self.tenant_setting('ANTHROPIC_API_KEY')
            client = AsyncAnthropic(api_key=tenant_key or api_key, max_retries=4)

        elif self.provider == APIProvider.VERTEX:
            client = AsyncAnthropicVertex()

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

            if not aws_region:
                raise ValueError('AWS_REGION is required for Bedrock provider')

            # Initialize with available credentials using explicit kwargs for clearer typing
            logger.info(f'Using AsyncAnthropicBedrock client with region: {aws_region}')
            client = AsyncAnthropicBedrock(
                aws_region=aws_region,
                aws_access_key=aws_access_key or None,
                aws_secret_key=aws_secret_key or None,
                aws_session_token=aws_session_token or None,
            )
        elif self.provider == APIProvider.LEGACYUSE_PROXY:
            proxy_key = self.tenant_setting('LEGACYUSE_PROXY_API_KEY') or getattr(
                settings, 'LEGACYUSE_PROXY_API_KEY', None
            )
            if not proxy_key:
                raise ValueError(
                    'LEGACYUSE_PROXY_API_KEY is required for LegacyUseClient'
                )
            client = LegacyUseClient(api_key=proxy_key)
            client = cast(AsyncAnthropic, client)
        else:
            raise ValueError(f'Unsupported Anthropic provider: {self.provider}')

        client = instructor.from_anthropic(client, max_retries=self.max_retries)
        return client

    def prepare_system(self, system_prompt: str) -> Iterable[BetaTextBlockParam]:
        """Prepare system prompt as Anthropic BetaTextBlockParam."""
        system = BetaTextBlockParam(type='text', text=system_prompt)

        # Add cache control for prompt caching
        if self.enable_prompt_caching:
            system['cache_control'] = {'type': 'ephemeral'}

        return [system]

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[BetaMessageParam]:
        """
        For Anthropic, messages are already in the correct format.
        Apply caching and image filtering if configured.
        """
        # Apply common preprocessing (image filtering only)
        messages = self.preprocess_messages(
            messages, image_truncation_threshold=self.image_truncation_threshold
        )

        # Apply Anthropic-specific prompt caching
        if self.enable_prompt_caching:
            inject_prompt_caching(messages)

        return messages

    def prepare_tools(
        self, tool_collection: ToolCollection
    ) -> list[BetaToolUnionParam]:
        """Convert tool collection to Anthropic format."""
        return tool_collection.to_params()

    def get_betas(self) -> list[str]:
        """Get list of Anthropic-specific beta flags."""
        betas = []
        if self.token_efficient_tools_beta:
            betas.append('token-efficient-tools-2025-02-19')
        if self.tool_beta_flag:
            betas.append(self.tool_beta_flag)
        if self.enable_prompt_caching:
            betas.append(PROMPT_CACHING_BETA_FLAG)
        return betas

    async def make_ai_request(
        self,
        client: instructor.AsyncInstructor,
        messages: list[BetaMessageParam],
        system: Iterable[BetaTextBlockParam],
        tools: list[BetaToolUnionParam],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> tuple[BetaMessage, httpx.Request, httpx.Response]:
        """Make raw API call to Anthropic and return provider-specific response."""
        betas = self.get_betas()

        logger.info(f'Messages: {self._truncate_for_debug(messages)}')

        raw_response = await client.beta.messages.with_raw_response.create(
            max_tokens=max_tokens,
            messages=messages,
            model=model,
            system=system,
            tools=tools,
            betas=betas,
            temperature=temperature,
            **kwargs,
        )

        parsed_response = cast(BetaMessage, raw_response.parse())

        return (
            parsed_response,
            raw_response.http_response.request,
            raw_response.http_response,
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
        """
        Make API call to Anthropic and return standardized response format.

        This is the public interface that calls the raw API and converts the response.
        Now handles conversions internally for a cleaner interface.
        """

        # Convert inputs to provider format if needed
        system_formatted = self.prepare_system(system)
        tools_formatted = self.prepare_tools(tools)
        messages_formatted = self.convert_to_provider_messages(messages)

        # Call the raw API
        parsed_response, request, raw_response = await self.make_ai_request(
            client=client,
            messages=messages_formatted,
            system=system_formatted,
            tools=tools_formatted,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        # Convert response to standardized format
        content_blocks, stop_reason = convert_from_provider_response(parsed_response)

        return content_blocks, stop_reason, request, raw_response

    def convert_from_provider_response(
        self, response: BetaMessage
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Convert Anthropic response to content blocks and stop reason.
        Response is already in Anthropic format.
        """
        return convert_from_provider_response(response)
