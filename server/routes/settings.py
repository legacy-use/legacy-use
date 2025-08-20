"""
Settings management routes.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.computer_use.config import (
    APIProvider,
    get_default_model_name,
)
from server.settings_tenant import get_tenant_setting, set_tenant_setting
from server.utils.db_dependencies import get_tenant_db
from server.utils.tenant_utils import get_tenant_from_request


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
async def get_providers(request: Request, db_tenant=Depends(get_tenant_db)):
    """Get available VLM providers and their configurations."""

    # Authenticate tenant (this will raise an exception if tenant is not found or inactive)
    tenant = get_tenant_from_request(request)
    tenant_schema = tenant['schema']

    # Define provider configurations using tenant settings
    provider_configs = {
        APIProvider.ANTHROPIC: {
            'name': 'Anthropic',
            'description': 'Anthropic Claude models via direct API',
            'available': bool(get_tenant_setting(tenant_schema, 'ANTHROPIC_API_KEY')),
            'credentials': {
                'api_key': obscure_api_key(
                    get_tenant_setting(tenant_schema, 'ANTHROPIC_API_KEY')
                ),
            },
        },
        APIProvider.BEDROCK: {
            'name': 'Amazon Bedrock',
            'description': 'Anthropic Claude models via AWS Bedrock',
            'available': all(
                [
                    get_tenant_setting(tenant_schema, 'AWS_ACCESS_KEY_ID'),
                    get_tenant_setting(tenant_schema, 'AWS_SECRET_ACCESS_KEY'),
                    get_tenant_setting(tenant_schema, 'AWS_REGION'),
                ]
            ),
            'credentials': {
                'access_key_id': obscure_api_key(
                    get_tenant_setting(tenant_schema, 'AWS_ACCESS_KEY_ID')
                ),
                'secret_access_key': obscure_api_key(
                    get_tenant_setting(tenant_schema, 'AWS_SECRET_ACCESS_KEY')
                ),
                'region': get_tenant_setting(tenant_schema, 'AWS_REGION'),
            },
        },
        APIProvider.VERTEX: {
            'name': 'Google Vertex AI',
            'description': 'Anthropic Claude models via Google Vertex AI',
            'available': all(
                [
                    get_tenant_setting(tenant_schema, 'VERTEX_REGION'),
                    get_tenant_setting(tenant_schema, 'VERTEX_PROJECT_ID'),
                ]
            ),
            'credentials': {
                'region': get_tenant_setting(tenant_schema, 'VERTEX_REGION'),
                'project_id': obscure_api_key(
                    get_tenant_setting(tenant_schema, 'VERTEX_PROJECT_ID')
                ),
            },
        },
        APIProvider.LEGACYUSE_PROXY: {
            'name': 'legacy-use Cloud',
            'description': 'Anthropic Claude models via legacy-use Cloud',
            'available': bool(
                get_tenant_setting(tenant_schema, 'LEGACYUSE_PROXY_API_KEY')
            ),
            'credentials': {
                'proxy_api_key': obscure_api_key(
                    get_tenant_setting(tenant_schema, 'LEGACYUSE_PROXY_API_KEY')
                ),
            },
        },
        APIProvider.OPENAI: {
            'name': 'OpenAI',
            'description': 'OpenAI GPT models via direct API',
            'available': bool(get_tenant_setting(tenant_schema, 'OPENAI_API_KEY')),
            'credentials': {
                'api_key': obscure_api_key(
                    get_tenant_setting(tenant_schema, 'OPENAI_API_KEY')
                ),
            },
        },
        APIProvider.OPENCUA: {
            'name': 'OpenCua',
            'description': 'OpenCua models via self-hosted AWS Sagemaker',
            'available': bool(get_tenant_setting(tenant_schema, 'AWS_ACCESS_KEY_ID')),
            'credentials': {
                'access_key_id': obscure_api_key(
                    get_tenant_setting(tenant_schema, 'AWS_ACCESS_KEY_ID')
                ),
                'secret_access_key': obscure_api_key(
                    get_tenant_setting(tenant_schema, 'AWS_SECRET_ACCESS_KEY')
                ),
                'region': get_tenant_setting(tenant_schema, 'AWS_REGION'),
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
        current_provider=get_tenant_setting(tenant_schema, 'API_PROVIDER'),
        providers=providers,
    )


@settings_router.post('/providers', response_model=Dict[str, str])
async def update_provider_settings(
    request: UpdateProviderRequest,
    http_request: Request,
    db_tenant=Depends(get_tenant_db),
):
    """Update provider configuration and set as active provider."""

    # Authenticate tenant (this will raise an exception if tenant is not found or inactive)
    tenant = get_tenant_from_request(http_request)
    tenant_schema = tenant['schema']

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
        set_tenant_setting(
            tenant_schema, 'ANTHROPIC_API_KEY', request.credentials['api_key']
        )

    elif provider_enum == APIProvider.BEDROCK:
        required_fields = ['access_key_id', 'secret_access_key', 'region']
        for field in required_fields:
            if field not in request.credentials:
                raise HTTPException(
                    status_code=400, detail=f'{field} is required for Bedrock provider'
                )
        set_tenant_setting(
            tenant_schema, 'AWS_ACCESS_KEY_ID', request.credentials['access_key_id']
        )
        set_tenant_setting(
            tenant_schema,
            'AWS_SECRET_ACCESS_KEY',
            request.credentials['secret_access_key'],
        )
        set_tenant_setting(tenant_schema, 'AWS_REGION', request.credentials['region'])

    elif provider_enum == APIProvider.VERTEX:
        required_fields = ['project_id', 'region']
        for field in required_fields:
            if field not in request.credentials:
                raise HTTPException(
                    status_code=400, detail=f'{field} is required for Vertex provider'
                )
        set_tenant_setting(
            tenant_schema, 'VERTEX_PROJECT_ID', request.credentials['project_id']
        )
        set_tenant_setting(
            tenant_schema, 'VERTEX_REGION', request.credentials['region']
        )

    elif provider_enum == APIProvider.LEGACYUSE_PROXY:
        if 'proxy_api_key' not in request.credentials:
            raise HTTPException(
                status_code=400,
                detail='API key is required for legacy-use Cloud provider',
            )
        set_tenant_setting(
            tenant_schema,
            'LEGACYUSE_PROXY_API_KEY',
            request.credentials['proxy_api_key'],
        )

    elif provider_enum == APIProvider.OPENAI:
        api_key = request.credentials.get('api_key', '')
        if not isinstance(api_key, str) or not api_key.strip():
            raise HTTPException(
                status_code=400, detail='API key is required for OpenAI provider'
            )
        set_tenant_setting(tenant_schema, 'OPENAI_API_KEY', api_key.strip())

    elif provider_enum == APIProvider.OPENCUA:
        required_fields = ['access_key_id', 'secret_access_key', 'region', 'endpoint']
        for field in required_fields:
            if field not in request.credentials:
                raise HTTPException(
                    status_code=400, detail=f'{field} is required for OpenCua provider'
                )
        set_tenant_setting(
            tenant_schema, 'AWS_ACCESS_KEY_ID', request.credentials['access_key_id']
        )
        set_tenant_setting(
            tenant_schema,
            'AWS_SECRET_ACCESS_KEY',
            request.credentials['secret_access_key'],
        )
        set_tenant_setting(tenant_schema, 'AWS_REGION', request.credentials['region'])

    # Set as active provider
    set_tenant_setting(tenant_schema, 'API_PROVIDER', provider_enum.value)

    return {
        'status': 'success',
        'message': f'Provider {request.provider} configured successfully',
    }
