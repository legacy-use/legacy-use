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
)

from server.computer_use.tools import ToolCollection, ToolResult


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
    def parse_tool_use(self, content_block: BetaContentBlockParam) -> Optional[dict]:
        """
        Parse tool use information from a content block.

        Args:
            content_block: A content block that may contain tool use

        Returns:
            Tool use information if found, None otherwise
        """
        ...

    @abstractmethod
    def make_tool_result(
        self, result: ToolResult, tool_use_id: str
    ) -> BetaContentBlockParam:
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
