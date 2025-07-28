import re
from typing import Optional

from fastapi import HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from server.utils.tenant import get_tenant_by_api_key
from server.database.models import TenantModel


class TenantNotFoundError(HTTPException):
    """Exception raised when tenant is not found."""
    def __init__(self):
        super().__init__(
            status_code=HTTP_403_FORBIDDEN,
            detail="Tenant not found or inactive"
        )


async def get_api_key(request: Request) -> str:
    """
    Getter function that extracts the API key from the request.
    """
    # Check if key is in header
    x_api_key = request.headers.get('X-API-Key')
    if x_api_key:
        return x_api_key

    # Check if key is in query params
    query_params = dict(request.query_params)
    if 'api_key' in query_params:
        return query_params.get('api_key')

    # if pattern r'^/sessions/.+/vnc/.+$' check in cookies for vnc_auth_<session_id>=<api_key>
    result = re.match(r'^/(api/)?sessions/(.+)/vnc/(.+$)', request.url.path)
    if result:
        session_id = result.group(2)
        vnc_auth_cookie_name = f'vnc_auth_{session_id}'
        cookie_key = request.cookies.get(vnc_auth_cookie_name)
        if cookie_key:
            return cookie_key

    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail='API key is missing')


async def get_current_tenant(request: Request) -> TenantModel:
    """
    Get the current tenant based on the API key in the request.
    This replaces the old API key validation with tenant-based authentication.
    """
    api_key = await get_api_key(request)
    
    # Get tenant by API key
    tenant = get_tenant_by_api_key(api_key)
    
    if not tenant:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail='Invalid API key'
        )
    
    if tenant.status != 'active':
        raise TenantNotFoundError()
    
    return tenant


def extract_subdomain(host: str) -> Optional[str]:
    """
    Extract subdomain from host header.
    Examples:
    - tenant1.example.com -> tenant1
    - localhost:8000 -> None (no subdomain)
    - 127.0.0.1:8000 -> None (no subdomain)
    """
    # Remove port if present
    host_without_port = host.split(':')[0]
    
    # Skip if it's an IP address or localhost
    if (host_without_port == 'localhost' or 
        host_without_port.replace('.', '').isdigit() or
        '.' not in host_without_port):
        return None
    
    # Extract subdomain (everything before the first dot)
    parts = host_without_port.split('.')
    if len(parts) > 2:  # has subdomain
        return parts[0]
    
    return None


async def get_tenant_from_subdomain(request: Request) -> Optional[TenantModel]:
    """
    Get tenant from subdomain in the host header.
    This is an alternative way to identify tenants for web interface.
    """
    host = request.headers.get('host', '')
    subdomain = extract_subdomain(host)
    
    if not subdomain:
        return None
    
    from server.utils.tenant import get_tenant_by_subdomain
    return get_tenant_by_subdomain(subdomain)
