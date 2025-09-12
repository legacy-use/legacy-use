"""
API definition and execution routes.
"""

import logging
import traceback
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.core import APIGatewayCore
from server.models.base import APIDefinition, CustomAction, Parameter
from server.settings import settings
from server.utils.api_definitions import (
    get_api_parameters,
    get_api_response_example,
    get_api_response_schema,
)
from server.utils.db_dependencies import get_tenant_db
from server.utils.telemetry import (
    capture_api_created,
    capture_api_deleted,
    capture_api_updated,
)

# Set up logging
logger = logging.getLogger(__name__)

# Create router
api_router = APIRouter(prefix='/api')  # Removed the tags=["API"] to prevent duplication


class APIDefinitionWithSchema(APIDefinition):
    response_schema: dict[str, Any]


@api_router.get(
    '/definitions',
    response_model=List[APIDefinitionWithSchema],
    tags=['API Definitions'],
)
async def get_api_definitions(
    include_archived: bool = False, db_tenant=Depends(get_tenant_db)
):
    """Get all available API definitions."""
    # Get API definitions from database

    # Get all API definitions, including archived if requested
    api_definitions = await db_tenant.get_api_definitions(include_archived)

    # Convert to API definition objects
    return [
        APIDefinitionWithSchema(
            name=api_def.name,
            description=api_def.description,
            parameters=await get_api_parameters(api_def, db_tenant),
            response_example=await get_api_response_example(api_def, db_tenant),
            response_schema=await get_api_response_schema(api_def, db_tenant),
            is_archived=api_def.is_archived,
        )
        for api_def in api_definitions
    ]


@api_router.get(
    '/definitions/{api_name}', response_model=APIDefinition, tags=['API Definitions']
)
async def get_api_definition(
    api_name: str, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Get a specific API definition by name."""
    # Get tenant schema for APIGatewayCore
    from server.utils.tenant_utils import get_tenant_from_request

    tenant = get_tenant_from_request(request)

    # Initialize the core API Gateway with tenant-aware database
    core = APIGatewayCore(tenant_schema=tenant['schema'], db_tenant=db_tenant)

    # Load API definitions fresh from the database
    api_definitions = await core.load_api_definitions()

    if api_name not in api_definitions:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    api = api_definitions[api_name]
    return APIDefinition(
        name=api.name,
        description=api.description,
        parameters=[Parameter(**param) for param in api.parameters],
        response_example=api.response_example,
    )


@api_router.get(
    '/definitions/{api_name}/export',
    response_model=Dict[str, Dict[str, Any]],
    tags=['API Definitions'],
)
async def export_api_definition(
    api_name: str, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Get a specific API definition in its raw format for export/backup purposes."""

    # First, check if the API exists and if it's archived
    api_definition_db = await db_tenant.get_api_definition_by_name(api_name)
    if not api_definition_db:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    # If the API is archived, get it directly from the database
    if api_definition_db.is_archived:
        # Get the latest version of the API definition
        version = await db_tenant.get_latest_api_definition_version(
            api_definition_db.id
        )
        if not version:
            raise HTTPException(
                status_code=404,
                detail=f"No versions found for API definition '{api_name}'",
            )

        # Return the API definition
        return {
            'api_definition': {
                'name': api_definition_db.name,
                'description': api_definition_db.description,
                'custom_actions': version.custom_actions,
                'parameters': version.parameters,
                'prompt': version.prompt,
                'prompt_cleanup': version.prompt_cleanup,
                'response_example': version.response_example,
            }
        }

    # For non-archived APIs, load fresh from the database
    # Get tenant schema for APIGatewayCore
    from server.utils.tenant_utils import get_tenant_from_request

    tenant = get_tenant_from_request(request)

    core = APIGatewayCore(tenant_schema=tenant['schema'], db_tenant=db_tenant)
    api_definitions = await core.load_api_definitions()

    if api_name not in api_definitions:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    api = api_definitions[api_name]
    return {
        'api_definition': {
            'name': api.name,
            'description': api.description,
            'custom_actions': api.custom_actions,
            'parameters': api.parameters,
            'prompt': api.prompt,
            'prompt_cleanup': api.prompt_cleanup,
            'response_example': api.response_example,
        }
    }


@api_router.get(
    '/definitions/{api_name}/versions',
    response_model=Dict[str, List[Dict[str, Any]]],
    tags=['API Definitions'],
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
async def get_api_definition_versions(api_name: str, db_tenant=Depends(get_tenant_db)):
    """Get all versions of a specific API definition."""

    # Get the API definition
    api_definition = await db_tenant.get_api_definition_by_name(api_name)
    if not api_definition:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    # Get all versions of the API definition
    versions = await db_tenant.get_api_definition_versions(
        api_definition.id, include_inactive=True
    )

    # Convert to list of dictionaries
    versions_list = []
    for version in versions:
        version_dict = {
            'id': str(version.id),
            'version_number': version.version_number,
            'parameters': version.parameters,
            'prompt': version.prompt,
            'prompt_cleanup': version.prompt_cleanup,
            'response_example': version.response_example,
            'created_at': version.created_at.isoformat(),
            'is_active': version.is_active,
        }
        versions_list.append(version_dict)

    # Sort by version number in descending order
    # Fix: Use a more robust approach with error handling
    def get_version_number(version_dict):
        try:
            return int(version_dict['version_number'])
        except (ValueError, TypeError):
            # If version_number is not a valid integer, return 0 as fallback
            return 0

    versions_list.sort(key=get_version_number, reverse=True)

    return {'versions': versions_list}


@api_router.get(
    '/definitions/{api_name}/versions/{version_id}',
    response_model=Dict[str, Dict[str, Any]],
    tags=['API Definitions'],
    include_in_schema=not settings.HIDE_INTERNAL_API_ENDPOINTS_IN_DOC,
)
async def get_api_definition_version(
    api_name: str, version_id: str, db_tenant=Depends(get_tenant_db)
):
    """Get a specific version of an API definition."""

    # Get the API definition
    api_definition = await db_tenant.get_api_definition_by_name(api_name)
    if not api_definition:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    # Get all versions of the API definition
    versions = await db_tenant.get_api_definition_versions(
        api_definition.id, include_inactive=True
    )

    # Find the specific version
    version = next((v for v in versions if str(v.id) == version_id), None)
    if not version:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{version_id}' not found for API '{api_name}'",
        )

    # Convert to dictionary
    version_dict = {
        'id': str(version.id),
        'version_number': version.version_number,
        'parameters': version.parameters,
        'prompt': version.prompt,
        'prompt_cleanup': version.prompt_cleanup,
        'response_example': version.response_example,
        'created_at': version.created_at.isoformat(),
        'is_active': version.is_active,
    }

    return {'version': version_dict}


class ImportApiDefinitionBody(BaseModel):
    name: str
    description: str
    parameters: List[Parameter]
    prompt: str
    prompt_cleanup: str
    response_example: Dict[str, Any]
    custom_actions: Optional[Dict[str, CustomAction]] = None


class ImportApiDefinitionRequest(BaseModel):
    api_definition: ImportApiDefinitionBody


@api_router.post(
    '/definitions/import', response_model=Dict[str, str], tags=['API Definitions']
)
async def import_api_definition(
    body: ImportApiDefinitionRequest, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Import an API definition from a JSON file."""
    try:
        api_def = body.api_definition

        # Check if API with this name already exists
        existing_api = await db_tenant.get_api_definition_by_name(api_def.name)
        api_id = ''
        version_number = ''

        if existing_api:
            # Create a new version for the existing API
            version_number = await db_tenant.get_next_version_number(existing_api.id)
            api_id = existing_api.id
            await db_tenant.create_api_definition_version(
                api_definition_id=existing_api.id,
                version_number=str(
                    version_number
                ),  # Convert to string to ensure consistency
                parameters=[param.model_dump() for param in api_def.parameters],
                custom_actions=api_def.custom_actions,
                prompt=api_def.prompt,
                prompt_cleanup=api_def.prompt_cleanup,
                response_example=api_def.response_example,
                is_active=True,  # Make this the active version
            )
            message = f"Updated existing API '{api_def.name}' with new version {version_number}"
        else:
            # Create a new API definition
            new_api_dict = await db_tenant.create_api_definition(
                name=api_def.name, description=api_def.description
            )

            api_id = new_api_dict['id']
            version_number = '1'  # Use string to ensure consistency
            # Create the first version
            await db_tenant.create_api_definition_version(
                api_definition_id=new_api_dict['id'],
                version_number=version_number,  # Use string to ensure consistency
                parameters=[param.model_dump() for param in api_def.parameters],
                custom_actions=api_def.custom_actions,
                prompt=api_def.prompt,
                prompt_cleanup=api_def.prompt_cleanup,
                response_example=api_def.response_example,
                is_active=True,
            )
            message = f"Created new API '{api_def.name}'"

        # Get tenant schema for APIGatewayCore
        from server.utils.tenant_utils import get_tenant_from_request

        tenant = get_tenant_from_request(request)

        # Reload API definitions in core
        core = APIGatewayCore(tenant_schema=tenant['schema'], db_tenant=db_tenant)
        await core.load_api_definitions()

        capture_api_created(request, api_def.model_dump(), api_id, str(version_number))
        return {'status': 'success', 'message': message, 'name': api_def.name}
    except Exception as e:
        logger.error(f'Error importing API definition: {str(e)}')
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f'Failed to import API definition: {str(e)}'
        ) from e


@api_router.put(
    '/definitions/{api_name}', response_model=Dict[str, str], tags=['API Definitions']
)
async def update_api_definition(
    api_name: str,
    body: ImportApiDefinitionRequest,
    request: Request,
    db_tenant=Depends(get_tenant_db),
):
    """Update an API definition."""
    try:
        api_def = body.api_definition

        # Check if API with this name exists
        existing_api = await db_tenant.get_api_definition_by_name(api_name)

        if not existing_api:
            raise HTTPException(
                status_code=404, detail=f"API definition '{api_name}' not found"
            )

        # Update the API definition name and description if changed
        if api_def.name != api_name:
            # Check if the new name already exists
            new_name_api = await db_tenant.get_api_definition_by_name(api_def.name)
            if new_name_api and new_name_api.id != existing_api.id:
                raise HTTPException(
                    status_code=400,
                    detail=f"API with name '{api_def.name}' already exists",
                )

            # Update the name
            await db_tenant.update_api_definition(existing_api.id, name=api_def.name)

        # Update the description if changed
        if api_def.description != existing_api.description:
            await db_tenant.update_api_definition(
                existing_api.id, description=api_def.description
            )

        # get all existing custom actions
        active_version = await db_tenant.get_active_api_definition_version(
            existing_api.id
        )
        print('active_version:', active_version)
        existing_custom_actions = db_tenant.get_custom_actions(active_version.id)
        print('existing_custom_actions:', existing_custom_actions)

        # Create a new version with the updated fields
        version_number = await db_tenant.get_next_version_number(existing_api.id)
        await db_tenant.create_api_definition_version(
            api_definition_id=existing_api.id,
            version_number=str(
                version_number
            ),  # Convert to string to ensure consistency
            parameters=[param.model_dump() for param in api_def.parameters],
            prompt=api_def.prompt,
            prompt_cleanup=api_def.prompt_cleanup,
            response_example=api_def.response_example,
            is_active=True,  # Make this the active version
            custom_actions=existing_custom_actions,
        )

        # Get tenant schema for APIGatewayCore
        from server.utils.tenant_utils import get_tenant_from_request

        tenant = get_tenant_from_request(request)

        # Reload API definitions in core
        core = APIGatewayCore(tenant_schema=tenant['schema'], db_tenant=db_tenant)
        await core.load_api_definitions()

        capture_api_updated(
            request, api_def.model_dump(), existing_api.id, str(version_number)
        )

        return {
            'status': 'success',
            'message': f"Updated API '{api_def.name}' with new version {version_number}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error updating API definition: {str(e)}')
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f'Failed to update API definition: {str(e)}'
        ) from e


@api_router.delete(
    '/definitions/{api_name}', response_model=Dict[str, str], tags=['API Definitions']
)
async def archive_api_definition(
    api_name: str, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Archive an API definition (soft delete)."""
    try:
        # Get the API definition
        api_definition = await db_tenant.get_api_definition_by_name(api_name)
        if not api_definition:
            raise HTTPException(
                status_code=404, detail=f"API definition '{api_name}' not found"
            )

        # Archive the API definition
        await db_tenant.archive_api_definition(api_definition.id)

        # Get tenant schema for APIGatewayCore
        from server.utils.tenant_utils import get_tenant_from_request

        tenant = get_tenant_from_request(request)

        # Reload API definitions in core
        core = APIGatewayCore(tenant_schema=tenant['schema'], db_tenant=db_tenant)
        await core.load_api_definitions()

        capture_api_deleted(request, api_definition.id, api_name)

        return {
            'status': 'success',
            'message': f"API '{api_name}' archived successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error archiving API definition: {str(e)}')
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f'Failed to archive API definition: {str(e)}'
        ) from e


@api_router.post(
    '/definitions/{api_name}/unarchive',
    response_model=Dict[str, str],
    tags=['API Definitions'],
)
async def unarchive_api_definition(
    api_name: str, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Unarchive an API definition."""
    try:
        # Get the API definition by name
        api_definition = await db_tenant.get_api_definition_by_name(api_name)
        if not api_definition:
            raise HTTPException(
                status_code=404, detail=f"API definition '{api_name}' not found"
            )

        # Unarchive the API definition
        await db_tenant.update_api_definition(api_definition.id, is_archived=False)

        # Get tenant schema for APIGatewayCore
        from server.utils.tenant_utils import get_tenant_from_request

        tenant = get_tenant_from_request(request)

        # Reload API definitions in core
        core = APIGatewayCore(tenant_schema=tenant['schema'], db_tenant=db_tenant)
        await core.load_api_definitions()

        return {
            'status': 'success',
            'message': f"API '{api_name}' unarchived successfully",
        }
    except Exception as e:
        logger.error(f'Error unarchiving API definition: {str(e)}')
        raise HTTPException(
            status_code=500, detail=f'Error unarchiving API definition: {str(e)}'
        ) from e


@api_router.get(
    '/definitions/{api_name}/metadata',
    response_model=Dict[str, Any],
    tags=['API Definitions'],
)
async def get_api_definition_metadata(api_name: str, db_tenant=Depends(get_tenant_db)):
    """Get metadata for a specific API definition, including archived status."""

    # Get the API definition
    api_definition = await db_tenant.get_api_definition_by_name(api_name)
    if not api_definition:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    # Return metadata
    return {
        'id': str(api_definition.id),
        'name': api_definition.name,
        'description': api_definition.description,
        'created_at': api_definition.created_at.isoformat(),
        'updated_at': api_definition.updated_at.isoformat(),
        'is_archived': api_definition.is_archived,
    }


# function to add a custom action to the api definition
@api_router.post(
    '/definitions/{api_name}/custom_actions',
    response_model=Dict[str, str],
    tags=['API Definitions'],
)
async def add_custom_action(
    api_name: str, custom_action: CustomAction, db_tenant=Depends(get_tenant_db)
):
    """Add a custom action to the API definition"""
    api_definition = await db_tenant.get_api_definition_by_name(api_name)

    if not api_definition:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    # Get the latest version of the API definition
    version = await db_tenant.get_latest_api_definition_version(api_definition.id)

    print('Appending custom action:', custom_action, 'to version:', version.id)
    # Add the custom action to the API definition
    success = db_tenant.append_custom_action(version.id, custom_action)
    if not success:
        raise HTTPException(status_code=500, detail='Failed to append custom action')

    return {
        'status': 'success',
        'message': f"Custom action '{custom_action.name}' added to API definition '{api_name}'",
    }


@api_router.get(
    '/definitions/{api_name}/custom_actions',
    response_model=Dict[str, Any],
    tags=['API Definitions'],
)
async def list_custom_actions(api_name: str, db_tenant=Depends(get_tenant_db)):
    """List custom actions for the latest version of an API definition."""
    api_definition = await db_tenant.get_api_definition_by_name(api_name)

    if not api_definition:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    version = await db_tenant.get_latest_api_definition_version(api_definition.id)
    actions = db_tenant.get_custom_actions(version.id)
    return {'status': 'success', 'actions': actions}


@api_router.delete(
    '/definitions/{api_name}/custom_actions/{action_name}',
    response_model=Dict[str, str],
    tags=['API Definitions'],
)
async def delete_custom_action(
    api_name: str, action_name: str, db_tenant=Depends(get_tenant_db)
):
    """Delete a custom action by name from the latest version of an API definition."""
    api_definition = await db_tenant.get_api_definition_by_name(api_name)
    if not api_definition:
        raise HTTPException(
            status_code=404, detail=f"API definition '{api_name}' not found"
        )

    version = await db_tenant.get_latest_api_definition_version(api_definition.id)
    actions: dict[str, CustomAction] = db_tenant.get_custom_actions(version.id)
    if action_name not in actions:
        raise HTTPException(status_code=404, detail='Custom action not found')
    # Remove and persist
    logger.info(f'Deleting custom action: {action_name}')
    actions.pop(action_name, None)
    logger.info(f'Updated custom actions: {actions}')
    ok = db_tenant.set_custom_actions(version.id, actions)
    if not ok:
        raise HTTPException(status_code=500, detail='Failed to update custom actions')
    return {'status': 'success', 'message': f"Custom action '{action_name}' deleted"}
