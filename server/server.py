"""
FastAPI server implementation for the API Gateway.
"""

import asyncio
import logging
import os

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration

from server.computer_use import APIProvider
from server.routes import (
    api_router,
    health_router,
    job_router,
    specs_router,
    target_router,
    teaching_mode_router,
    tools_router,
)
from server.routes.sessions import session_router, websocket_router
from server.routes.settings import settings_router
from server.settings_tenant import get_tenant_setting
from server.utils.api_prefix import api_prefix
from server.utils.auth import get_api_key
from server.utils.exceptions import TenantInactiveError, TenantNotFoundError
from server.utils.job_execution import initiate_graceful_shutdown, start_shared_workers
from server.utils.log_pruning import scheduled_log_pruning
from server.utils.maintenance_leader import (
    acquire_maintenance_leadership,
    release_maintenance_leadership,
)
from server.utils.session_monitor import start_session_monitor
from server.utils.telemetry import posthog_middleware
from server.utils.tenant_utils import get_tenant_from_request

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


def setup_provider_environment(tenant_schema: str):
    """Setup provider-specific environment variables for a tenant."""
    if not tenant_schema:
        raise ValueError('tenant_schema is required')

    # Use tenant-specific settings
    provider = get_tenant_setting(tenant_schema, 'API_PROVIDER')

    if provider == APIProvider.BEDROCK:
        aws_access_key = get_tenant_setting(tenant_schema, 'AWS_ACCESS_KEY_ID')
        aws_secret_key = get_tenant_setting(tenant_schema, 'AWS_SECRET_ACCESS_KEY')
        aws_region = get_tenant_setting(tenant_schema, 'AWS_REGION')

        if not all([aws_access_key, aws_secret_key, aws_region]):
            logger.warning('Using Bedrock provider but AWS credentials are missing.')
        else:
            os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key
            os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
            os.environ['AWS_REGION'] = aws_region
            logger.info(
                f'AWS credentials loaded for Bedrock provider (region: {aws_region})'
            )

    elif provider == APIProvider.VERTEX:
        vertex_region = get_tenant_setting(tenant_schema, 'VERTEX_REGION')
        vertex_project_id = get_tenant_setting(tenant_schema, 'VERTEX_PROJECT_ID')

        if not all([vertex_region, vertex_project_id]):
            logger.warning(
                'Using Vertex provider but required environment variables are missing.'
            )
        else:
            os.environ['CLOUD_ML_REGION'] = vertex_region
            os.environ['ANTHROPIC_VERTEX_PROJECT_ID'] = vertex_project_id
            logger.info(
                f'Vertex credentials loaded (region: {vertex_region}, project: {vertex_project_id})'
            )


app = FastAPI(
    title='AI API Gateway',
    description='API Gateway for AI-powered endpoints',
    version='1.0.0',
    redoc_url=f'{api_prefix}/redoc' if settings.SHOW_DOCS else None,
    docs_url=f'{api_prefix}/docs' if settings.SHOW_DOCS else None,
    openapi_url=f'{api_prefix}/openapi.json' if settings.SHOW_DOCS else None,
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

    if settings.SHOW_DOCS:
        whitelist_patterns.append(rf'^{api_prefix}/redoc(/.*)?$')
        whitelist_patterns.append(rf'^{api_prefix}/docs(/.*)?$')
        whitelist_patterns.append(rf'^{api_prefix}/specs(/.*)?$')
        whitelist_patterns.append(rf'^{api_prefix}/openapi.json$')

    # Check if request path matches any whitelist pattern
    for pattern in whitelist_patterns:
        if re.match(pattern, request.url.path):
            return await call_next(request)

    try:
        # We check for tenant first, so the web-app can redirect if no tenant is found
        tenant = get_tenant_from_request(request)
        tenant_schema = tenant['schema']
        api_key = await get_api_key(request)

        # Check if API key matches tenant-specific API key
        tenant_api_key = get_tenant_setting(tenant_schema, 'API_KEY')

        if api_key == tenant_api_key:
            return await call_next(request)
        else:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={'detail': 'Invalid API Key'},
            )
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={'detail': e.detail},
        )
    except TenantNotFoundError as e:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                'detail': 'Tenant not found',
                'error_type': 'tenant_not_found',
                'message': str(e),
            },
        )
    except TenantInactiveError as e:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                'detail': 'Tenant is inactive',
                'error_type': 'tenant_inactive',
                'message': str(e),
            },
        )


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
            'name': settings.API_KEY_NAME,
            'description': "API key authentication. Enter your API key in the format: 'your_api_key'",
        }
    }
}


# Exception handlers for multi-tenancy
@app.exception_handler(TenantNotFoundError)
async def tenant_not_found_handler(request: Request, exc: TenantNotFoundError):
    """Handle tenant not found errors."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            'detail': 'Tenant not found',
            'error_type': 'tenant_not_found',
            'message': str(exc),
        },
    )


@app.exception_handler(TenantInactiveError)
async def tenant_inactive_handler(request: Request, exc: TenantInactiveError):
    """Handle inactive tenant errors."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            'detail': 'Tenant is inactive',
            'error_type': 'tenant_inactive',
            'message': str(exc),
        },
    )


app.openapi_security = [{'ApiKeyAuth': []}]

# Include API router
app.include_router(api_router, prefix=api_prefix)

# Include teaching mode router
app.include_router(teaching_mode_router, prefix=api_prefix)

# Include core routers
app.include_router(target_router, prefix=api_prefix)
app.include_router(
    session_router,
    prefix=api_prefix,
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
app.include_router(job_router, prefix=api_prefix)

# Include WebSocket router
app.include_router(websocket_router, prefix=api_prefix)


# Include settings router
app.include_router(settings_router, prefix=api_prefix)

# Include specs router
app.include_router(specs_router, prefix=api_prefix)

# Include tools router
app.include_router(tools_router, prefix=api_prefix)

# Include monitoring router
app.include_router(health_router, prefix=api_prefix)


# Root endpoint
@app.get('/')
async def root():
    """Root endpoint."""
    return {'message': 'Welcome to the API Gateway'}


@app.on_event('startup')
async def startup_event():
    """Start background tasks on server startup."""
    # Check for SQLite database URL and abort if found
    database_url = settings.DATABASE_URL.lower()
    if 'sqlite' in database_url:
        error_message = """
SQLite support has been removed from this version of Legacy Use.

To migrate your data:
1. Restore the previous build that supported SQLite
2. Export your data using the API endpoints or database tools
3. Set up a PostgreSQL database
4. Import your data into PostgreSQL
5. Update your DATABASE_URL to point to PostgreSQL

Example PostgreSQL URL: postgresql://username:password@localhost:5432/database_name

For more information, please refer to the migration documentation.
"""
        logger.error(error_message)
        raise SystemExit(1)

    # Start background maintenance tasks only if we are the leader
    leader_key = 'legacy_use_maintenance_v1'
    if acquire_maintenance_leadership(leader_key):
        asyncio.create_task(scheduled_log_pruning())
        logger.info('Started background task for pruning old logs (leader)')

        start_session_monitor()
        logger.info('Started session state monitor (leader)')
    else:
        logger.info('Another process holds maintenance leadership; skipping monitors')

    # No need to load API definitions on startup anymore
    # They will be loaded on demand when needed

    # Start shared worker loops so any existing queued jobs are processed on boot
    await start_shared_workers()
    logger.info('Started shared worker loops')


@app.on_event('shutdown')
async def shutdown_event():
    """Gracefully drain workers on shutdown (SIGTERM)."""
    try:
        timeout = getattr(settings, 'SHUTDOWN_GRACE_PERIOD_SECONDS', 300)
        await initiate_graceful_shutdown(timeout_seconds=timeout)
    except Exception as e:
        logger.error(f'Error during graceful shutdown: {e}')
    finally:
        # Release leadership if held
        try:
            release_maintenance_leadership('legacy_use_maintenance_v1')
        except Exception:
            pass


if __name__ == '__main__':
    import uvicorn

    host = settings.FASTAPI_SERVER_HOST
    port = settings.FASTAPI_SERVER_PORT
    uvicorn.run('server.server:app', host=host, port=port, reload=True)
