"""
Routes package for the API Gateway.
"""

from .diagnostics import diagnostics_router
from .api import api_router
from .ai import ai_router
from .jobs import job_router
from .targets import target_router
from .sessions import session_router, websocket_router
from .settings import settings_router

__all__ = [
    'api_router',
    'ai_router',
    'target_router',
    'session_router',
    'job_router',
    'websocket_router',
    'diagnostics_router',
    'settings_router',
]
