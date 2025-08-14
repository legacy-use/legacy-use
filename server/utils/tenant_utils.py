"""
Tenant utilities for multi-tenancy support.
"""

from typing import Dict, List

from fastapi import Request

from server.database.multi_tenancy import get_tenant_by_host
from server.database.shared import db_shared
from server.utils.exceptions import TenantInactiveError, TenantNotFoundError


def get_tenant_from_request(request: Request) -> Dict[str, str]:
    """
    Extract tenant information from the request.

    Args:
        request: FastAPI request object

    Returns:
        Dictionary containing tenant information (name, schema, etc.)

    Raises:
        TenantNotFoundError: If no tenant is found for the host
        TenantInactiveError: If the tenant is inactive
    """
    # Extract host from request headers
    host = request.headers.get('host', '')

    if not host:
        raise TenantNotFoundError('No host header found in request')

    # Remove port if present
    if ':' in host:
        host = host.split(':')[0]

    # Look up tenant by host
    tenant = get_tenant_by_host(host)

    if not tenant:
        raise TenantNotFoundError(f'No tenant found for host: {host}')

    if not tenant.is_active:
        raise TenantInactiveError(f'Tenant {tenant.name} is inactive')

    # Return tenant information as dictionary
    return {
        'id': str(tenant.id),
        'name': tenant.name,
        'host': tenant.host,
        'schema': tenant.schema,
        'is_active': tenant.is_active,
    }


def get_active_tenants() -> List[Dict]:
    """
    Get all active tenants from the database.

    Returns:
        List of active tenant dictionaries
    """
    return db_shared.list_tenants(include_inactive=False)
