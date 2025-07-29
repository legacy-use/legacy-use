import re
from typing import Optional

from fastapi import HTTPException, Request, Depends
from fastapi.security import APIKeyHeader, APIKeyQuery, APIKeyCookie
from fastapi.security.base import SecurityBase
from starlette.status import HTTP_401_UNAUTHORIZED

from server.settings import settings


# Define security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


class VNCCookieAuth(SecurityBase):
    """Custom security scheme for VNC authentication via cookies"""
    
    def __init__(self):
        self.model = None
        self.scheme_name = "VNC Cookie Auth"


vnc_cookie_auth = VNCCookieAuth()


async def get_vnc_cookie_key(request: Request) -> Optional[str]:
    """Extract VNC auth cookie for specific session endpoints"""
    result = re.match(r'^/(api/)?sessions/(.+)/vnc/(.+$)', request.url.path)
    if result:
        session_id = result.group(2)
        vnc_auth_cookie_name = f'vnc_auth_{session_id}'
        return request.cookies.get(vnc_auth_cookie_name)
    return None


async def get_api_key(
    request: Request,
    api_key_header_val: Optional[str] = Depends(api_key_header),
    api_key_query_val: Optional[str] = Depends(api_key_query),
    vnc_cookie_key: Optional[str] = Depends(get_vnc_cookie_key)
) -> str:
    """
    Extract and validate API key from various sources using FastAPI dependencies.
    
    Priority order:
    1. X-API-Key header
    2. api_key query parameter  
    3. VNC session cookie (for VNC endpoints only)
    """
    # Check header first
    if api_key_header_val:
        return api_key_header_val
    
    # Check query params
    if api_key_query_val:
        return api_key_query_val
    
    # Check VNC cookie for VNC endpoints
    if vnc_cookie_key:
        return vnc_cookie_key
    
    raise HTTPException(
        status_code=HTTP_401_UNAUTHORIZED, 
        detail="API key is missing. Provide it via X-API-Key header, api_key query parameter, or VNC session cookie."
    )


async def validate_api_key(api_key: str = Depends(get_api_key)) -> str:
    """Validate the extracted API key against the configured key"""
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return api_key


# Dependency for endpoints that require authentication
require_api_key = Depends(validate_api_key)
