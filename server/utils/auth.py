import re

from fastapi import HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED

from server.config import config


async def get_api_key(request: Request):
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
    if re.match(r'^/sessions/.+/vnc/.+$', request.url.path):
        cookies = request.cookies
        session_id = request.url.path.split('/')[2]
        for cookie in cookies:
            if cookie.startswith('vnc_auth_') and session_id in cookie:
                return cookies.get(cookie)

    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail='API key is missing')
