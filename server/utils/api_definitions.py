"""
Utility functions for working with API definitions.

These helpers encapsulate common database lookups for API definition
parameters, response examples, and response schemas.
"""

from typing import Any, Dict


def infer_schema_from_response_example(response_example: Any) -> Dict[str, Any]:
    """Infer a best-effort OpenAPI 3.1-compatible JSON Schema from an example value.

    Handles nested objects, arrays, and primitive types. For arrays with
    heterogeneous item types, produces an ``anyOf`` for ``items``.
    ``None`` values are treated as a union with ``null`` as a conservative default.
    """

    def infer(value: Any) -> Dict[str, Any]:
        # Objects
        if isinstance(value, dict):
            return {
                'type': 'object',
                'properties': {key: infer(val) for key, val in value.items()},
            }

        # Arrays
        if isinstance(value, list):
            if not value:
                return {'type': 'array', 'items': {'type': 'string'}}

            # Collect unique schemas from array items
            unique_item_schemas = []
            for item in value:
                schema = infer(item)
                if schema not in unique_item_schemas:
                    unique_item_schemas.append(schema)

            if len(unique_item_schemas) == 1:
                return {'type': 'array', 'items': unique_item_schemas[0]}
            return {'type': 'array', 'items': {'anyOf': unique_item_schemas}}

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
            # OpenAPI 3.1 / JSON Schema: use a type union with "null"
            return {'type': ['string', 'null']}

        # Fallback
        return {'type': 'string'}

    schema = infer(response_example)

    # Add description to the schema if it's an object
    if isinstance(schema, dict) and schema.get('type') == 'object':
        schema.setdefault('description', 'API response')

    return schema


async def get_api_parameters(api_def_id, db_tenant):
    """Get parameters for an API definition's active version."""
    version = await db_tenant.get_active_api_definition_version(api_def_id)
    return version.parameters if version else []


async def get_api_response_example(api_def_id, db_tenant):
    """Get response example for an API definition's active version."""
    version = await db_tenant.get_active_api_definition_version(api_def_id)
    return version.response_example if version else {}


async def get_api_response_schema(api_def_id, db_tenant):
    """Get response schema for an API definition's active version."""
    version = await db_tenant.get_active_api_definition_version(api_def_id)
    response_example = version.response_example if version else {}

    # infer schema from response example
    return infer_schema_from_response_example(response_example)


async def get_api_response_schema_by_version_id(api_def_version_id, db_tenant):
    """Get response schema for an API definition's version."""
    version = await db_tenant.get_api_definition_version(api_def_version_id)
    response_example = version.response_example if version else {}

    # infer schema from response example
    return infer_schema_from_response_example(response_example)
