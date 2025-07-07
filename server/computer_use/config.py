"""
Configuration for Computer Use API Gateway.
"""

from server.models.api_provider import (
    APIProvider,
    PROVIDER_TO_DEFAULT_MODEL_NAME,
    get_default_model_name,
    get_tool_version,
    validate_provider,
)

# Beta feature flags
COMPUTER_USE_BETA_FLAG = 'computer-use-2024-10-22'
PROMPT_CACHING_BETA_FLAG = 'prompt-caching-2024-07-31'
