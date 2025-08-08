"""
Handler registry for managing provider-specific handlers.

This module provides the registry and factory functions for instantiating
the appropriate handler based on the API provider.
"""

from typing import Dict, Optional, Type

from server.computer_use.config import APIProvider
from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.logging import logger
from server.computer_use.handlers.openai import OpenAIHandler
from server.computer_use.handlers.openai_cua import OpenAICUAHandler

# Registry mapping providers to handler classes
HANDLER_REGISTRY: Dict[APIProvider, Type[BaseProviderHandler]] = {}


def register_handler(provider: APIProvider, handler_class: Type[BaseProviderHandler]):
    """
    Register a handler class for a specific provider.

    Args:
        provider: The API provider enum value
        handler_class: The handler class to register
    """
    HANDLER_REGISTRY[provider] = handler_class
    logger.info(f'Registered handler {handler_class.__name__} for provider {provider}')


def get_handler(
    provider: APIProvider,
    model: str,
    tool_beta_flag: Optional[str] = None,
    token_efficient_tools_beta: bool = False,
    only_n_most_recent_images: Optional[int] = None,
    **kwargs,
) -> BaseProviderHandler:
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
    # Lazy import to avoid circular dependency
    from server.computer_use.handlers.anthropic import AnthropicHandler

    # Register handlers if not already done
    if not HANDLER_REGISTRY:
        # Register Anthropic handler for all Anthropic-based providers
        register_handler(APIProvider.ANTHROPIC, AnthropicHandler)
        register_handler(APIProvider.BEDROCK, AnthropicHandler)
        register_handler(APIProvider.VERTEX, AnthropicHandler)
        register_handler(APIProvider.LEGACYUSE_PROXY, AnthropicHandler)

        # OpenAI handler can be registered when ready for use:
        register_handler(APIProvider.OPENAI, OpenAIHandler)
        register_handler(APIProvider.OPENAI_CUA, OpenAICUAHandler)

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

    # Remove provider from kwargs if the handler doesn't expect it
    if handler_class != AnthropicHandler:
        handler_kwargs.pop('provider', None)

    return handler_class(**handler_kwargs)
