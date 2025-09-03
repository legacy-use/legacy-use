"""
Tools routes.
"""

from fastapi import APIRouter

from server.computer_use.handlers.utils.key_mapping_utils import KEY_ALIASES
from server.computer_use.tools.groups import TOOL_GROUPS_BY_VERSION

tools_router = APIRouter(prefix='/tools')


@tools_router.get('/group/{group_name}')
async def get_tools_group(group_name: str):
    """Get all tools for a given group."""
    tool_group = TOOL_GROUPS_BY_VERSION[group_name]
    tool_specifications = [tool().internal_spec() for tool in tool_group.tools]
    return {'status': 'success', 'message': tool_specifications}


@tools_router.get('/keys')
async def get_keys():
    """Get all keys."""
    try:
        return {'status': 'success', 'message': list(KEY_ALIASES.keys())}
    except Exception as e:
        return {'status': 'error', 'message': f'Error getting keys: {e}'}
