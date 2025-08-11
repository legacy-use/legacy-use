"""
Routes package for the API Gateway.
"""

from .diagnostics import diagnostics_router
from .api import api_router
from .teaching_mode import teaching_mode_router
from .jobs import job_router
from .targets import target_router
from .sessions import session_router, websocket_router
from .settings import settings_router
from .specs import specs_router

__all__ = [
    'api_router',
    'teaching_mode_router',
    'target_router',
    'session_router',
    'job_router',
    'websocket_router',
    'diagnostics_router',
    'settings_router',
    'specs_router',
]
