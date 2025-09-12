"""
Utility functions for working with API definitions.

These helpers encapsulate common database lookups for API definition
parameters, response examples, and response schemas.
"""

from typing import Any, Dict, List


def infer_schema_from_response_example(response_example: Any) -> Dict[str, Any]:
    """Infer a best-effort OpenAPI-compatible JSON schema from an example value.

    Handles nested objects, arrays, and primitive types. For arrays with
    heterogeneous item types, produces an ``anyOf`` for ``items``. ``None``
    values are treated as nullable strings as a conservative default for
    OpenAPI 3.0.
    """

    def infer(value: Any) -> Dict[str, Any]:
        # Objects
        if isinstance(value, dict):
            properties: Dict[str, Any] = {key: infer(val) for key, val in value.items()}
            schema: Dict[str, Any] = {'type': 'object'}
            if properties:
                schema['properties'] = properties
            return schema

        # Arrays
        if isinstance(value, list):
            schema: Dict[str, Any] = {'type': 'array'}
            if not value:
                schema['items'] = {'type': 'string'}
                return schema

            item_schemas: List[Dict[str, Any]] = [infer(item) for item in value]

            # Deduplicate schemas by equality
            unique_item_schemas: List[Dict[str, Any]] = []
            for s in item_schemas:
                if s not in unique_item_schemas:
                    unique_item_schemas.append(s)

            if len(unique_item_schemas) == 1:
                schema['items'] = unique_item_schemas[0]
            else:
                schema['items'] = {'anyOf': unique_item_schemas}
            return schema

        # Primitives
        if isinstance(value, bool):
            return {'type': 'boolean'}
        if isinstance(value, int):
            return {'type': 'integer'}
        if isinstance(value, float):
            return {'type': 'number'}
        if isinstance(value, str):
            return {'type': 'string'}
        if value is None:
            return {'type': 'string', 'nullable': True}

        # Fallback
        return {'type': 'string'}

    schema = infer(response_example)
    if isinstance(schema, dict) and schema.get('type') == 'object':
        schema.setdefault('description', 'API response')
    return schema


async def get_api_parameters(api_def, db_tenant):
    """Get parameters for an API definition's active version."""
    version = await db_tenant.get_active_api_definition_version(api_def.id)
    return version.parameters if version else []


async def get_api_response_example(api_def, db_tenant):
    """Get response example for an API definition's active version."""
    version = await db_tenant.get_active_api_definition_version(api_def.id)
    return version.response_example if version else {}


async def get_api_response_schema(api_def, db_tenant):
    """Get response schema for an API definition's active version."""
    version = await db_tenant.get_active_api_definition_version(api_def.id)
    response_example = version.response_example if version else {}

    # infer schema from response example
    return infer_schema_from_response_example(response_example)
