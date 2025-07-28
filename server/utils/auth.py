import re

from fastapi import HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED


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
    result = re.match(r'^/(api/)?sessions/(.+)/vnc/(.+$)', request.url.path)
    if result:
        session_id = result.group(2)
        vnc_auth_cookie_name = f'vnc_auth_{session_id}'
        return request.cookies.get(vnc_auth_cookie_name)

    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail='API key is missing')
