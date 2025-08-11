from server.settings import settings


def get_api_prefix():
    """Normalized api slug prefix, based on settings.API_SLUG_PREFIX."""
    api_prefix = settings.API_SLUG_PREFIX.strip()
    if not api_prefix.startswith('/'):
        api_prefix = '/' + api_prefix
    return api_prefix.rstrip('/')


api_prefix = get_api_prefix()
