"""
OpenAPI schema generator for custom API definitions from database.
This module converts database API definitions into OpenAPI 3.0 schema format
for beautiful documentation rendering with Redoc.
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime

from server.database import db
from server.models.base import Parameter


class CustomOpenAPIGenerator:
    """Generate OpenAPI schema from database API definitions."""
    
    def __init__(self):
        self.base_schema = {
            "openapi": "3.0.0",
            "info": {
                "title": "Custom API Definitions",
                "description": "Documentation for custom API definitions stored in the database",
                "version": "1.0.0"
            },
            "servers": [
                {
                    "url": "/api",
                    "description": "API Gateway Server"
                }
            ],
            "paths": {},
            "components": {
                "schemas": {},
                "parameters": {},
                "responses": {}
            }
        }
    
    async def generate_openapi_schema(self, include_archived: bool = False) -> Dict[str, Any]:
        """Generate complete OpenAPI schema from database API definitions."""
        schema = self.base_schema.copy()
        schema["paths"] = {}
        schema["components"]["schemas"] = {}
        
        # Get all API definitions from database
        api_definitions = await db.get_api_definitions(include_archived)
        
        for api_def in api_definitions:
            if api_def.is_archived and not include_archived:
                continue
                
            # Get active version for this API definition
            version = await db.get_active_api_definition_version(api_def.id)
            if not version:
                continue
            
            # Generate path for this API definition
            path_item = await self._generate_path_item(api_def, version)
            schema["paths"][f"/execute/{api_def.name}"] = path_item
            
            # Generate schema components
            request_schema = self._generate_request_schema(api_def.name, version.parameters)
            response_schema = self._generate_response_schema(api_def.name, version.response_example)
            
            schema["components"]["schemas"][f"{api_def.name}Request"] = request_schema
            schema["components"]["schemas"][f"{api_def.name}Response"] = response_schema
        
        return schema
    
    async def _generate_path_item(self, api_def, version) -> Dict[str, Any]:
        """Generate OpenAPI path item for an API definition."""
        return {
            "post": {
                "summary": api_def.name,
                "description": api_def.description,
                "tags": ["Custom APIs"],
                "operationId": f"execute_{api_def.name}",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": f"#/components/schemas/{api_def.name}Request"
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Successful execution",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{api_def.name}Response"
                                }
                            }
                        }
                    },
                    "400": {
                        "description": "Bad request - invalid parameters"
                    },
                    "404": {
                        "description": "API definition not found"
                    },
                    "500": {
                        "description": "Internal server error"
                    }
                },
                "x-api-version": version.version_number,
                "x-created-at": api_def.created_at.isoformat() if api_def.created_at else None,
                "x-updated-at": api_def.updated_at.isoformat() if api_def.updated_at else None
            }
        }
    
    def _generate_request_schema(self, api_name: str, parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate OpenAPI schema for request parameters."""
        properties = {}
        required = []
        
        for param in parameters:
            param_name = param.get("name", "")
            param_type = param.get("type", "string")
            param_description = param.get("description", "")
            param_default = param.get("default")
            
            # Convert parameter type to OpenAPI type
            openapi_type = self._convert_param_type_to_openapi(param_type)
            
            property_schema = {
                "type": openapi_type["type"],
                "description": param_description
            }
            
            # Add format if specified
            if "format" in openapi_type:
                property_schema["format"] = openapi_type["format"]
            
            # Add array items if it's an array type
            if openapi_type["type"] == "array":
                property_schema["items"] = openapi_type.get("items", {"type": "string"})
            
            # Add default value if provided
            if param_default is not None:
                property_schema["default"] = param_default
            else:
                required.append(param_name)
            
            properties[param_name] = property_schema
        
        schema = {
            "type": "object",
            "properties": properties
        }
        
        if required:
            schema["required"] = required
            
        return schema
    
    def _generate_response_schema(self, api_name: str, response_example: Dict[str, Any]) -> Dict[str, Any]:
        """Generate OpenAPI schema for response based on example."""
        if not response_example:
            return {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Execution status"
                    },
                    "result": {
                        "type": "object",
                        "description": "API execution result"
                    }
                }
            }
        
        # Generate schema from example structure
        return self._infer_schema_from_example(response_example)
    
    def _infer_schema_from_example(self, example: Any) -> Dict[str, Any]:
        """Infer OpenAPI schema from example data."""
        if isinstance(example, dict):
            properties = {}
            for key, value in example.items():
                properties[key] = self._infer_schema_from_example(value)
            
            return {
                "type": "object",
                "properties": properties
            }
        elif isinstance(example, list):
            if example:
                items_schema = self._infer_schema_from_example(example[0])
            else:
                items_schema = {"type": "string"}
            
            return {
                "type": "array",
                "items": items_schema
            }
        elif isinstance(example, str):
            return {"type": "string"}
        elif isinstance(example, int):
            return {"type": "integer"}
        elif isinstance(example, float):
            return {"type": "number"}
        elif isinstance(example, bool):
            return {"type": "boolean"}
        else:
            return {"type": "string"}
    
    def _convert_param_type_to_openapi(self, param_type: str) -> Dict[str, Any]:
        """Convert parameter type to OpenAPI type specification."""
        type_mapping = {
            "string": {"type": "string"},
            "str": {"type": "string"},
            "integer": {"type": "integer"},
            "int": {"type": "integer"},
            "number": {"type": "number"},
            "float": {"type": "number", "format": "float"},
            "boolean": {"type": "boolean"},
            "bool": {"type": "boolean"},
            "array": {"type": "array", "items": {"type": "string"}},
            "list": {"type": "array", "items": {"type": "string"}},
            "object": {"type": "object"},
            "dict": {"type": "object"},
            "date": {"type": "string", "format": "date"},
            "datetime": {"type": "string", "format": "date-time"},
            "email": {"type": "string", "format": "email"},
            "uri": {"type": "string", "format": "uri"},
            "uuid": {"type": "string", "format": "uuid"}
        }
        
        return type_mapping.get(param_type.lower(), {"type": "string"})


# Global instance
openapi_generator = CustomOpenAPIGenerator()