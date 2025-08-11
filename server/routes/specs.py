"""
API specifications routes.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from scalar_fastapi import get_scalar_api_reference

from server.utils.api_prefix import api_prefix
from server.utils.db_dependencies import get_tenant_db
from server.utils.specs import (
    convert_api_definition_to_openapi_path,
    openapi_spec,
)

specs_router = APIRouter(prefix='/specs')


@specs_router.get('/')
async def scalar_html():
    openapi_url = f'{api_prefix}/{specs_router.prefix}/openapi.json'.replace('//', '/')

    return get_scalar_api_reference(
        openapi_url=openapi_url,
        title='API Gateway Specifications',
    )


@specs_router.get('/openapi.json')
async def get_openapi_specs(db_tenant=Depends(get_tenant_db)):
    """
    Get API specifications in OpenAPI format.

    Returns all active API definitions from the database as OpenAPI compatible specifications.
    """
    # Get all non-archived API definitions with versions eagerly loaded
    api_definitions = await db_tenant.get_api_definitions_with_versions(
        include_archived=False
    )

    # Convert each API definition to OpenAPI format
    for api_def in api_definitions:
        # Get the active version for this API definition
        active_version = None
        for version in api_def.versions:
            if version.is_active:
                active_version = version
                break

        if not active_version:
            continue  # Skip if no active version

        # Create path for this API
        path_key = f'/api/{api_def.name}'
        path_value = convert_api_definition_to_openapi_path(api_def, active_version)
        openapi_spec['paths'][path_key] = path_value

    return JSONResponse(content=openapi_spec)
