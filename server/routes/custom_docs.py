"""
Custom documentation routes for rendering internal API models as beautiful documentation.
This module provides endpoints to serve custom Redoc documentation for database API definitions.
"""

from fastapi import APIRouter, Response, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional

from server.utils.openapi_generator import openapi_generator
from server.settings import settings

# Create router
docs_router = APIRouter()


@docs_router.get("/custom-api-docs", response_class=HTMLResponse)
async def custom_api_docs(include_archived: Optional[bool] = Query(default=False)):
    """
    Serve custom Redoc documentation for internal API definitions from database.
    This endpoint renders the internal API models as beautiful endpoint definitions.
    """
    # Generate the custom OpenAPI schema URL
    schema_url = f"/custom-openapi.json?include_archived={include_archived}"
    
    # Create custom Redoc HTML
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Custom API Documentation</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
        <style>
            body {{
                margin: 0;
                padding: 0;
            }}
        </style>
    </head>
    <body>
        <redoc spec-url='{schema_url}'></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@2.1.3/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@docs_router.get("/custom-openapi.json")
async def custom_openapi_schema(include_archived: Optional[bool] = Query(default=False)):
    """
    Generate and serve custom OpenAPI schema for internal API definitions.
    This schema is consumed by the custom Redoc documentation.
    """
    try:
        # Generate OpenAPI schema from database API definitions
        schema = await openapi_generator.generate_openapi_schema(include_archived)
        
        return JSONResponse(content=schema)
    
    except Exception as e:
        # Return error schema if generation fails
        error_schema = {
            "openapi": "3.0.0",
            "info": {
                "title": "Custom API Definitions - Error",
                "description": f"Failed to generate API documentation: {str(e)}",
                "version": "1.0.0"
            },
            "paths": {},
            "components": {
                "schemas": {}
            }
        }
        
        return JSONResponse(content=error_schema, status_code=500)


@docs_router.get("/api-definitions-summary")
async def api_definitions_summary(include_archived: Optional[bool] = Query(default=False)):
    """
    Get a summary of available API definitions for quick reference.
    This endpoint provides metadata about the custom APIs without full OpenAPI schema.
    """
    from server.database import db
    
    try:
        # Get all API definitions from database
        api_definitions = await db.get_api_definitions(include_archived)
        
        summary = []
        for api_def in api_definitions:
            # Get active version for this API definition
            version = await db.get_active_api_definition_version(api_def.id)
            
            summary_item = {
                "name": api_def.name,
                "description": api_def.description,
                "is_archived": api_def.is_archived,
                "created_at": api_def.created_at.isoformat() if api_def.created_at else None,
                "updated_at": api_def.updated_at.isoformat() if api_def.updated_at else None,
                "version": version.version_number if version else None,
                "parameter_count": len(version.parameters) if version else 0,
                "has_response_example": bool(version.response_example) if version else False
            }
            
            summary.append(summary_item)
        
        return {
            "total_count": len(summary),
            "active_count": len([item for item in summary if not item["is_archived"]]),
            "archived_count": len([item for item in summary if item["is_archived"]]),
            "api_definitions": summary
        }
    
    except Exception as e:
        return JSONResponse(
            content={"error": f"Failed to get API definitions summary: {str(e)}"},
            status_code=500
        )