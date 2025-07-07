"""
FastAPI server implementation for the API Gateway.
"""

import asyncio
import logging
from datetime import datetime, timedelta

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from starlette.status import HTTP_401_UNAUTHORIZED

from server.computer_use import APIProvider, validate_provider
from server.config import config
from server.database import db
from server.routes import api_router, job_router, target_router
from server.routes.diagnostics import diagnostics_router
from server.routes.sessions import session_router, websocket_router
from server.utils.auth import get_api_key
from server.utils.job_execution import job_queue_initializer
from server.utils.session_monitor import start_session_monitor
from server.utils.telemetry import posthog_middleware

# Set up logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate essential environment variables
try:
    config.validate_essential_variables()
except ValueError as e:
    logger.error(f"Environment validation failed: {e}")
    raise

# Initialize Sentry
if config.API_SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.API_SENTRY_DSN,
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
        environment=config.ENVIRONMENT,
    )
    logger.info('Sentry initialized for backend')
else:
    logger.warning(
        'API_SENTRY_DSN not found in environment variables. Sentry is disabled.'
    )

# API Key security
API_KEY = config.API_KEY
API_KEY_NAME = 'X-API-Key'

# Validate and setup AI provider
provider = validate_provider(config.API_PROVIDER)

# Validate AI provider-specific settings
try:
    config.validate_ai_provider_settings()
    config.setup_provider_environment()
    logger.info(f'AI provider configured: {config.API_PROVIDER}')
except ValueError as e:
    logger.error(f"AI provider validation failed: {e}")
    raise

# Handle provider-specific logging
if provider == APIProvider.BEDROCK:
    if config.AWS_REGION:
        logger.info(f'AWS credentials loaded for Bedrock provider (region: {config.AWS_REGION})')
elif provider == APIProvider.VERTEX:
    if config.VERTEX_REGION and config.VERTEX_PROJECT_ID:
        logger.info(f'Vertex credentials loaded (region: {config.VERTEX_REGION}, project: {config.VERTEX_PROJECT_ID})')


app = FastAPI(
    title='AI API Gateway',
    description='API Gateway for AI-powered endpoints',
    version='1.0.0',
    redoc_url='/redoc' if config.SHOW_DOCS else None,
    # Disable automatic redirect from /path to /path/
    redirect_slashes=False,
)


@app.middleware('http')
async def telemetry_middleware(request: Request, call_next):
    return await posthog_middleware(request, call_next)


@app.middleware('http')
async def auth_middleware(request: Request, call_next):
    import re

    # Allow CORS preflight requests (OPTIONS) to pass through without authentication
    if request.method == 'OPTIONS':
        return await call_next(request)

    # auth whitelist (regex patterns)
    whitelist_patterns = [
        r'^/favicon\.ico$',  # Favicon requests
        r'^/robots\.txt$',  # Robots.txt requests
        r'^/sitemap\.xml$',  # Sitemap requests
    ]

    if config.SHOW_DOCS:
        whitelist_patterns.append(
            r'^/redoc(/.*)?$'
        )  # Matches /redoc and /redoc/anything
        whitelist_patterns.append(r'^/openapi.json$')  # Needed for docs

    # Check if request path matches any whitelist pattern
    for pattern in whitelist_patterns:
        if re.match(pattern, request.url.path):
            return await call_next(request)

    api_key = await get_api_key(request)
    if api_key == API_KEY:
        return await call_next(request)

    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail='Invalid API Key')


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
        'ApiKeyAuth': {
            'type': 'apiKey',
            'in': 'header',
            'name': API_KEY_NAME,
            'description': "API key authentication. Enter your API key in the format: 'your_api_key'",
        }
    }
}

app.openapi_security = [{'ApiKeyAuth': []}]

# Include API router
app.include_router(api_router)

# Include core routers
app.include_router(target_router)
app.include_router(
    session_router, include_in_schema=not config.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC
)
app.include_router(job_router)

# Include WebSocket router
app.include_router(websocket_router)

# Include diagnostics router
app.include_router(
    diagnostics_router, include_in_schema=not config.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC
)


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
            days_to_keep = config.LOG_RETENTION_DAYS
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

    port = config.FASTAPI_SERVER_PORT
    uvicorn.run('server.server:app', host='0.0.0.0', port=port, reload=True)
