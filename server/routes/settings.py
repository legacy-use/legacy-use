"""
Settings management routes.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from server.computer_use.config import (
    APIProvider,
    get_default_model_name,
)
from server.settings import settings
from server.utils.auth import require_api_key


def obscure_api_key(api_key: Optional[str]) -> Optional[str]:
    """
    Obscure an API key by showing only the last 4 characters.

    Args:
        api_key: The API key to obscure

    Returns:
        Obscured API key showing only last 4 digits, or None if key is None/empty
    """
    if not api_key or len(api_key) < 4:
        return None

    return f'****{api_key[-4:]}'


class ProviderConfiguration(BaseModel):
    """Configuration for a VLM provider."""

    provider: str
    name: str
    default_model: str
    available: bool
    description: str
    credentials: Dict[str, Optional[str]]


class ProvidersResponse(BaseModel):
    """Response model for providers endpoint."""

    current_provider: str
    providers: List[ProviderConfiguration]


class UpdateProviderRequest(BaseModel):
    """Request model for updating provider configuration."""

    provider: str
    credentials: Dict[str, str]


# Create router
settings_router = APIRouter(prefix='/settings', tags=['Settings'])


@settings_router.get('/providers', response_model=ProvidersResponse)
async def get_providers(_: str = require_api_key):
    """Get available VLM providers and their configurations."""

    # workaround to reload settings after updating the provider
    settings.__init__()

    # Define provider configurations
    provider_configs = {
        APIProvider.ANTHROPIC: {
            'name': 'Anthropic',
            'description': 'Anthropic Claude models via direct API',
            'available': bool(getattr(settings, 'ANTHROPIC_API_KEY', None)),
            'credentials': {
                'api_key': obscure_api_key(
                    getattr(settings, 'ANTHROPIC_API_KEY', None)
                ),
            },
        },
        APIProvider.BEDROCK: {
            'name': 'Amazon Bedrock',
            'description': 'Anthropic Claude models via AWS Bedrock',
            'available': all(
                [
                    getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                    getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                    getattr(settings, 'AWS_REGION', None),
                ]
            ),
            'credentials': {
                'access_key_id': obscure_api_key(
                    getattr(settings, 'AWS_ACCESS_KEY_ID', None)
                ),
                'secret_access_key': obscure_api_key(
                    getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
                ),
                'region': getattr(settings, 'AWS_REGION', None),
            },
        },
        APIProvider.VERTEX: {
            'name': 'Google Vertex AI',
            'description': 'Anthropic Claude models via Google Vertex AI',
            'available': all(
                [
                    getattr(settings, 'VERTEX_REGION', None),
                    getattr(settings, 'VERTEX_PROJECT_ID', None),
                ]
            ),
            'credentials': {
                'region': getattr(settings, 'VERTEX_REGION', None),
                'project_id': obscure_api_key(
                    getattr(settings, 'VERTEX_PROJECT_ID', None)
                ),
            },
        },
        APIProvider.LEGACYUSE_PROXY: {
            'name': 'legacy-use Cloud',
            'description': 'Anthropic Claude models via legacy-use Cloud',
            'available': bool(getattr(settings, 'LEGACYUSE_PROXY_API_KEY', None)),
            'credentials': {
                'proxy_api_key': obscure_api_key(
                    getattr(settings, 'LEGACYUSE_PROXY_API_KEY', None)
                ),
            },
        },
    }

    # Build provider list
    providers = []
    for provider_enum, config in provider_configs.items():
        providers.append(
            ProviderConfiguration(
                provider=provider_enum.value,
                name=config['name'],
                default_model=get_default_model_name(provider_enum),
                available=config['available'],
                description=config['description'],
                credentials=config['credentials'],
            )
        )

    return ProvidersResponse(
        current_provider=settings.API_PROVIDER, providers=providers
    )


@settings_router.post('/providers', response_model=Dict[str, str])
async def update_provider_settings(request: UpdateProviderRequest, _: str = require_api_key):
    """Update provider configuration and set as active provider."""

    # Validate provider
    try:
        provider_enum = APIProvider(request.provider)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f'Invalid provider: {request.provider}'
        )

    # Update settings based on provider type
    if provider_enum == APIProvider.ANTHROPIC:
        if 'api_key' not in request.credentials:
            raise HTTPException(
                status_code=400, detail='API key is required for Anthropic provider'
            )
        settings.ANTHROPIC_API_KEY = request.credentials['api_key']

    elif provider_enum == APIProvider.BEDROCK:
        required_fields = ['access_key_id', 'secret_access_key', 'region']
        for field in required_fields:
            if field not in request.credentials:
                raise HTTPException(
                    status_code=400, detail=f'{field} is required for Bedrock provider'
                )
        settings.AWS_ACCESS_KEY_ID = request.credentials['access_key_id']
        settings.AWS_SECRET_ACCESS_KEY = request.credentials['secret_access_key']
        settings.AWS_REGION = request.credentials['region']

    elif provider_enum == APIProvider.VERTEX:
        required_fields = ['project_id', 'region']
        for field in required_fields:
            if field not in request.credentials:
                raise HTTPException(
                    status_code=400, detail=f'{field} is required for Vertex provider'
                )
        settings.VERTEX_PROJECT_ID = request.credentials['project_id']
        settings.VERTEX_REGION = request.credentials['region']

    elif provider_enum == APIProvider.LEGACYUSE_PROXY:
        if 'proxy_api_key' not in request.credentials:
            raise HTTPException(
                status_code=400,
                detail='API key is required for legacy-use Cloud provider',
            )
        settings.LEGACYUSE_PROXY_API_KEY = request.credentials['proxy_api_key']

    # Set as active provider
    settings.API_PROVIDER = provider_enum.value

    return {
        'status': 'success',
        'message': f'Provider {request.provider} configured successfully',
    }
