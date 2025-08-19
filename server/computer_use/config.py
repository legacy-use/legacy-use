"""
Configuration for Computer Use API Gateway.
"""

from enum import StrEnum

from server.computer_use.tools.groups import ToolVersion

# Beta feature flags
COMPUTER_USE_BETA_FLAG = 'computer-use-2024-10-22'
PROMPT_CACHING_BETA_FLAG = 'prompt-caching-2024-07-31'


class APIProvider(StrEnum):
    ANTHROPIC = 'anthropic'
    BEDROCK = 'bedrock'
    VERTEX = 'vertex'
    LEGACYUSE_PROXY = 'legacyuse'
    OPENAI = 'openai'
    OPENCUA = 'opencua'


PROVIDER_TO_DEFAULT_MODEL_NAME: dict[APIProvider, str] = {
    APIProvider.ANTHROPIC: 'claude-sonnet-4-20250514',
    APIProvider.BEDROCK: 'eu.anthropic.claude-sonnet-4-20250514-v1:0',
    APIProvider.VERTEX: 'claude-sonnet-4@20250514',
    APIProvider.LEGACYUSE_PROXY: 'legacy-use-sonnet-4',  # model selection is handled server side
    APIProvider.OPENAI: 'gpt-5',
    APIProvider.OPENCUA: 'opencua-7b-1234567890',
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


def get_tool_version(model_name: str) -> ToolVersion:
    """
    Get the tool version for a given model name.
    """
    # if needed 'computer_use_20241022', dependend on the model name, but currently all models are 20250124
    return 'computer_use_20250124'
