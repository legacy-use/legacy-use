"""
FastAPI server implementation for the API Gateway.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration

from server.computer_use import APIProvider
from server.database import db
from server.routes import api_router, job_router, target_router
from server.routes.diagnostics import diagnostics_router
from server.routes.sessions import session_router, websocket_router
from server.routes.settings import settings_router
from server.utils.auth import api_key_header, api_key_query, vnc_cookie_auth
from server.utils.job_execution import job_queue_initializer
from server.utils.session_monitor import start_session_monitor
from server.utils.telemetry import posthog_middleware

from .settings import settings

# Set up logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Sentry
if settings.API_SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.API_SENTRY_DSN,
        integrations=[
            FastApiIntegration(),
            AsyncioIntegration(),
        ],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=0.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        profiles_sample_rate=0.0,
        # Environment
        environment=settings.ENVIRONMENT,
    )
    logger.info('Sentry initialized for backend')
else:
    logger.warning(
        'API_SENTRY_DSN not found in environment variables. Sentry is disabled.'
    )


# Handle provider-specific environment variables
if settings.API_PROVIDER == APIProvider.BEDROCK:
    if not all(
        [
            settings.AWS_ACCESS_KEY_ID,
            settings.AWS_SECRET_ACCESS_KEY,
            settings.AWS_REGION,
        ]
    ):
        logger.warning('Using Bedrock provider but AWS credentials are missing.')
    else:
        # Export AWS credentials to environment if using Bedrock
        # Ensure these are set in environment for the AnthropicBedrock client
        os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
        os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
        os.environ['AWS_REGION'] = settings.AWS_REGION
        logger.info(
            f'AWS credentials loaded for Bedrock provider (region: {settings.AWS_REGION})'
        )
elif settings.API_PROVIDER == APIProvider.VERTEX:
    # Get Vertex-specific environment variables

    if not all([settings.VERTEX_REGION, settings.VERTEX_PROJECT_ID]):
        logger.warning(
            'Using Vertex provider but required environment variables are missing.'
        )
    else:
        # Ensure these are set in environment for the AnthropicVertex client
        os.environ['CLOUD_ML_REGION'] = settings.VERTEX_REGION
        os.environ['ANTHROPIC_VERTEX_PROJECT_ID'] = settings.VERTEX_PROJECT_ID
        logger.info(
            f'Vertex credentials loaded (region: {settings.VERTEX_REGION}, project: {settings.VERTEX_PROJECT_ID})'
        )


app = FastAPI(
    title='AI API Gateway',
    description='API Gateway for AI-powered endpoints',
    version='1.0.0',
    redoc_url='/redoc' if settings.SHOW_DOCS else None,
    # Disable automatic redirect from /path to /path/
    redirect_slashes=False,
)


@app.middleware('http')
async def telemetry_middleware(request: Request, call_next):
    return await posthog_middleware(request, call_next)


# Authentication is now handled via FastAPI dependencies on individual routes
# Static files and documentation endpoints don't require authentication


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        '*'
    ],  # Allows all origins; TODO: restrict to specific origins -> need to think of a way to handle "external" requests
    allow_credentials=True,
    allow_methods=[
        'GET',
        'POST',
        'PUT',
        'DELETE',
        'PATCH',
        'OPTIONS',
    ],  # Restrict to common HTTP methods
    allow_headers=[
        'Content-Type',
        'Authorization',
        'X-API-Key',
        'X-Distinct-Id',  # For telemetry/analytics
        'Accept',
        'Accept-Language',
        'Content-Language',
        'Cache-Control',
        'Origin',
        'X-Requested-With',
    ],  # Restrict to necessary headers
    expose_headers=[
        'Content-Type',
        'X-Total-Count',
    ],  # Only expose necessary response headers
)

# Add API key security scheme to OpenAPI
app.openapi_tags = [
    {'name': 'API Definitions', 'description': 'API definition endpoints'},
]

app.openapi_components = {
    'securitySchemes': {
        'ApiKeyHeader': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'X-API-Key',
            'description': "API key authentication via header. Enter your API key.",
        },
        'ApiKeyQuery': {
            'type': 'apiKey',
            'in': 'query',
            'name': 'api_key',
            'description': "API key authentication via query parameter.",
        },
        'VNCCookieAuth': {
            'type': 'apiKey',
            'in': 'cookie',
            'name': 'vnc_auth_{session_id}',
            'description': "VNC session authentication via cookie (for VNC endpoints only).",
        }
    }
}

# Security is now applied per-endpoint via dependencies rather than globally

# Include API router
app.include_router(api_router)

# Include core routers
app.include_router(target_router)
app.include_router(
    session_router,
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
app.include_router(job_router)

# Include WebSocket router
app.include_router(websocket_router)

# Include diagnostics router
app.include_router(
    diagnostics_router,
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)

# Include settings router
app.include_router(settings_router)


# Root endpoint
@app.get('/')
async def root():
    """Root endpoint."""
    return {'message': 'Welcome to the API Gateway'}


# Scheduled task to prune old logs
async def prune_old_logs():
    """Prune logs older than 7 days."""
    while True:
        try:
            # Sleep until next pruning time (once a day at midnight)
            now = datetime.now()
            next_run = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sleep_seconds = (next_run - now).total_seconds()
            logger.info(
                f'Next log pruning scheduled in {sleep_seconds / 3600:.1f} hours'
            )
            await asyncio.sleep(sleep_seconds)

            # Prune logs
            days_to_keep = settings.LOG_RETENTION_DAYS
            deleted_count = db.prune_old_logs(days=days_to_keep)
            logger.info(f'Pruned {deleted_count} logs older than {days_to_keep} days')
        except Exception as e:
            logger.error(f'Error pruning logs: {str(e)}')
            await asyncio.sleep(3600)  # Sleep for an hour and try again


@app.on_event('startup')
async def startup_event():
    """Start background tasks on server startup."""
    # Start background tasks
    asyncio.create_task(prune_old_logs())
    logger.info('Started background task for pruning old logs')

    # Start session monitor
    start_session_monitor()
    logger.info('Started session state monitor')

    # No need to load API definitions on startup anymore
    # They will be loaded on demand when needed

    # Initialize job queue from database
    await job_queue_initializer()
    logger.info('Initialized job queue from database')


if __name__ == '__main__':
    import uvicorn

    host = settings.FASTAPI_SERVER_HOST
    port = settings.FASTAPI_SERVER_PORT
    uvicorn.run('server.server:app', host=host, port=port, reload=True)
