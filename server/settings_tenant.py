"""
Tenant-specific settings management.

This module provides a simple getter function for tenant-specific settings
that were previously stored in global environment variables.
"""

from typing import Optional

from server.database.models import TenantSettings
from server.database.multi_tenancy import with_db

# Define the tenant-specific settings that were previously global
TENANT_SETTINGS_DEFAULTS = {
    'API_KEY': 'not-secure-api-key',
    'API_PROVIDER': 'anthropic',
    'AWS_ACCESS_KEY_ID': None,
    'AWS_SECRET_ACCESS_KEY': None,
    'AWS_REGION': None,
    'AWS_SESSION_TOKEN': None,
    'ANTHROPIC_API_KEY': None,
    'OPENAI_API_KEY': None,
    'VERTEX_PROJECT_ID': None,
    'VERTEX_REGION': None,
    'LEGACYUSE_PROXY_API_KEY': None,
    # Google Gemini settings
    'GOOGLE_API_KEY': None,  # Google AI Studio API key
    'GOOGLE_CLOUD_PROJECT': None,  # Vertex AI project ID
    'GOOGLE_CLOUD_LOCATION': None,  # Vertex AI region (default: us-central1)
}


def get_tenant_setting(tenant_schema: str, key: str) -> Optional[str]:
    """
    Get a tenant-specific setting.

    Args:
        tenant_schema: The tenant schema name
        key: The setting key to retrieve

    Returns:
        The setting value if found in database, otherwise the default value
    """
    if key not in TENANT_SETTINGS_DEFAULTS:
        raise ValueError(f'Unknown tenant setting key: {key}')

    default_value = TENANT_SETTINGS_DEFAULTS[key]

    with with_db(tenant_schema) as db_tenant:
        setting = (
            db_tenant.query(TenantSettings).filter(TenantSettings.key == key).first()
        )
        return setting.value if setting else default_value


def set_tenant_setting(tenant_schema: str, key: str, value: str) -> None:
    """
    Set a tenant-specific setting.

    Args:
        tenant_schema: The tenant schema name
        key: The setting key to set
        value: The value to set
    """
    if key not in TENANT_SETTINGS_DEFAULTS:
        raise ValueError(f'Unknown tenant setting key: {key}')

    with with_db(tenant_schema) as db_tenant:
        setting = (
            db_tenant.query(TenantSettings).filter(TenantSettings.key == key).first()
        )

        if setting:
            setting.value = value
        else:
            setting = TenantSettings(key=key, value=value)
            db_tenant.add(setting)

        db_tenant.commit()
