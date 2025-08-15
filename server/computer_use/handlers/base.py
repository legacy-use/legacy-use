"""
Base handler protocol for LLM provider implementations.

This module defines the abstract interface that all provider handlers must implement
to support multi-provider functionality in the sampling loop.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Protocol, runtime_checkable

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaToolResultBlockParam,
)

from server.computer_use.tools import ToolCollection, ToolResult
from server.settings_tenant import get_tenant_setting as _get_tenant_setting
from server.computer_use.utils import (
    _inject_prompt_caching,
    _maybe_filter_to_n_most_recent_images,
)


@runtime_checkable
class ProviderHandler(Protocol):
    """Protocol defining the interface for LLM provider handlers."""

    @abstractmethod
    async def initialize_client(self, api_key: str, **kwargs) -> Any:
        """
        Initialize and return the provider-specific client.

        Args:
            api_key: API key for the provider
            **kwargs: Additional provider-specific configuration

        Returns:
            The initialized client instance
        """
        ...

    @abstractmethod
    def prepare_system(self, system_prompt: str) -> Any:
        """
        Prepare the system prompt in provider-specific format.

        Args:
            system_prompt: The system prompt text

        Returns:
            System prompt in provider-specific format
        """
        ...

    @abstractmethod
    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[Any]:
        """
        Convert Anthropic-format messages to provider-specific format.

        Args:
            messages: List of messages in Anthropic BetaMessageParam format

        Returns:
            List of messages in provider-specific format
        """
        ...

    @abstractmethod
    def prepare_tools(self, tool_collection: ToolCollection) -> Any:
        """
        Prepare tools in provider-specific format.

        Args:
            tool_collection: Collection of available tools

        Returns:
            Tools in provider-specific format
        """
        ...

    @abstractmethod
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
        """
        Make the API call to the provider.

        Args:
            client: The provider client instance
            messages: Messages in provider format
            system: System prompt in provider format
            tools: Tools in provider format
            model: Model identifier
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
            **kwargs: Additional provider-specific parameters

        Returns:
            Tuple of (parsed_response, request, raw_response)
        """
        ...

    @abstractmethod
    def convert_from_provider_response(
        self, response: Any
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Convert provider response to Anthropic-format blocks and stop reason.

        Args:
            response: The provider's parsed response

        Returns:
            Tuple of (content_blocks, stop_reason)
        """
        ...

    @abstractmethod
    def make_tool_result(
        self, result: ToolResult, tool_use_id: str
    ) -> BetaToolResultBlockParam:
        """
        Create a tool result block in Anthropic format.

        Args:
            result: The tool execution result
            tool_use_id: ID of the tool use

        Returns:
            Tool result in Anthropic BetaContentBlockParam format
        """
        ...


class BaseProviderHandler(ABC):
    """Base class with common functionality for provider handlers."""

    def __init__(
        self,
        token_efficient_tools_beta: bool = False,
        only_n_most_recent_images: Optional[int] = None,
        enable_prompt_caching: bool = False,
        tenant_schema: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the handler with common parameters.

        Args:
            token_efficient_tools_beta: Whether to use token-efficient tools
            only_n_most_recent_images: Number of recent images to keep
            enable_prompt_caching: Whether to enable prompt caching
            **kwargs: Additional provider-specific parameters
        """
        self.token_efficient_tools_beta = token_efficient_tools_beta
        self.only_n_most_recent_images = only_n_most_recent_images
        self.enable_prompt_caching = enable_prompt_caching
        self.tenant_schema = tenant_schema
        self.extra_params = kwargs

    def get_betas(self) -> list[str]:
        """Get list of beta flags for the provider."""
        betas = []
        if self.token_efficient_tools_beta:
            betas.append('token-efficient-tools-2025-02-19')
        if self.enable_prompt_caching:
            from server.computer_use.config import PROMPT_CACHING_BETA_FLAG

            betas.append(PROMPT_CACHING_BETA_FLAG)
        return betas

    def tenant_setting(self, key: str) -> Optional[str]:
        """Convenience accessor for tenant-specific settings."""
        if not self.tenant_schema:
            return None
        return _get_tenant_setting(self.tenant_schema, key)

    def preprocess_messages(
        self,
        messages: list[BetaMessageParam],
        *,
        image_truncation_threshold: int = 1,
    ) -> list[BetaMessageParam]:
        """Apply common preprocessing such as prompt caching and image trimming.

        This returns the same list object with modifications applied in-place
        where appropriate, and also returns it for convenience.
        """
        # Prompt caching markers
        if self.enable_prompt_caching:
            _inject_prompt_caching(messages)

        # Optional image trimming
        if self.only_n_most_recent_images:
            _maybe_filter_to_n_most_recent_images(
                messages,
                self.only_n_most_recent_images,
                min_removal_threshold=image_truncation_threshold,
            )

        return messages
