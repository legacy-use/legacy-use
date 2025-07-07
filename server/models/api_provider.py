"""
API Provider configuration.
"""

from enum import StrEnum


class APIProvider(StrEnum):
    ANTHROPIC = 'anthropic'
    BEDROCK = 'bedrock'
    VERTEX = 'vertex'


PROVIDER_TO_DEFAULT_MODEL_NAME: dict[APIProvider, str] = {
    APIProvider.ANTHROPIC: 'claude-sonnet-4-20250514',
    APIProvider.BEDROCK: 'eu.anthropic.claude-sonnet-4-20250514-v1:0',
    APIProvider.VERTEX: 'claude-sonnet-4@20250514',
}


def validate_provider(provider_str: str) -> APIProvider:
    """
    Validate and convert a provider string to an APIProvider enum value.

    Args:
        provider_str: String representation of the provider (e.g., "anthropic", "bedrock")

    Returns:
        APIProvider enum value

    Raises:
        ValueError: If the provider is invalid
    """
    try:
        return getattr(APIProvider, provider_str.upper())
    except (AttributeError, TypeError):
        # Fallback to default provider if invalid
        return APIProvider.ANTHROPIC


def get_default_model_name(provider: APIProvider) -> str:
    """
    Get the default model name for a given provider.
    """
    return PROVIDER_TO_DEFAULT_MODEL_NAME[provider]


def get_tool_version(model_name: str) -> str:
    """
    Get the tool version for a given model name.
    """
    if '3-7' in model_name or 'sonnet-4' in model_name:
        return 'computer_use_20250124'
    return 'computer_use_20241022' 