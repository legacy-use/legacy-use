"""
Handler registry for managing provider-specific handlers.

This module provides the registry and factory functions for instantiating
the appropriate handler based on the API provider.
"""

from typing import Dict, Optional, Type

from server.computer_use.config import APIProvider
from server.computer_use.handlers.anthropic.handler import AnthropicHandler
from server.computer_use.handlers.base import BaseProviderHandler, ProviderHandler
from server.computer_use.handlers.gemini.handler import GeminiHandler
from server.computer_use.handlers.openai.handler import OpenAIHandler
from server.computer_use.handlers.opencua.handler import OpenCuaHandler

# Registry mapping providers to handler classes
HANDLER_REGISTRY: Dict[APIProvider, Type[BaseProviderHandler]] = {
    APIProvider.ANTHROPIC: AnthropicHandler,
    APIProvider.BEDROCK: AnthropicHandler,
    APIProvider.VERTEX: AnthropicHandler,
    APIProvider.LEGACYUSE_PROXY: AnthropicHandler,
    APIProvider.OPENAI: OpenAIHandler,
    APIProvider.OPENCUA: OpenCuaHandler,
    APIProvider.GEMINI: GeminiHandler,
    APIProvider.GEMINI_VERTEX: GeminiHandler,
}


def get_handler(
    provider: APIProvider,
    model: str,
    tool_beta_flag: Optional[str] = None,
    token_efficient_tools_beta: bool = False,
    only_n_most_recent_images: Optional[int] = None,
    **kwargs,
) -> ProviderHandler:
    """
    Get an instance of the appropriate handler for the given provider.

    Args:
        provider: The API provider to use
        model: Model identifier
        tool_beta_flag: Tool-specific beta flag
        token_efficient_tools_beta: Whether to use token-efficient tools
        only_n_most_recent_images: Number of recent images to keep
        **kwargs: Additional provider-specific parameters

    Returns:
        An instance of the appropriate handler

    Raises:
        ValueError: If no handler is registered for the provider
    """

    handler_class = HANDLER_REGISTRY.get(provider)

    if not handler_class:
        raise ValueError(
            f'No handler registered for provider {provider}. '
            f'Available providers: {list(HANDLER_REGISTRY.keys())}'
        )

    # Instantiate the handler with the provided parameters
    handler_kwargs = {
        'provider': provider,
        'model': model,
        'tool_beta_flag': tool_beta_flag,
        'token_efficient_tools_beta': token_efficient_tools_beta,
        'only_n_most_recent_images': only_n_most_recent_images,
        **kwargs,
    }

    return handler_class(**handler_kwargs)  # type: ignore[return-value]
