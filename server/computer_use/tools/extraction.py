"""Extraction tool for returning JSON data."""

import json
import logging
from typing import Any, Dict, Hashable, Literal

from anthropic.types.beta import BetaToolUnionParam
from jsonschema import ValidationError
from openapi_schema_validator import OAS31Validator, validate

from .base import BaseAnthropicTool, ToolResult

logger = logging.getLogger('server')


class ExtractionTool(BaseAnthropicTool):
    """Tool for returning extracted JSON data."""

    name: Literal['extraction'] = 'extraction'

    def __init__(
        self, response_schema: Dict[Hashable, Any] | None = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        logger.info(
            f'Extraction tool initialized with response schema: {response_schema}'
        )
        self.response_schema = response_schema

    def to_params(self) -> BetaToolUnionParam:
        # TODO: Check if including response_schema improves the tool's performance
        return {
            'name': 'extraction',
            'description': "Use this tool to return the final JSON result when you've found the information requested by the user.",
            'input_schema': {
                'type': 'object',
                'properties': {
                    'data': {
                        'type': 'object',
                        'description': 'The extracted data to return as JSON',
                    }
                },
                'required': ['data'],
            },
        }

    async def __call__(self, *, data: Dict[str, Any]) -> ToolResult:
        """Process the extraction request."""
        try:
            # Log the raw extraction data first
            logger.info(f'Extraction tool called with raw data: {data}')

            # Check if we received the data inside a 'data' field
            if 'data' in data:
                extraction_data = data['data']
                logger.info(f"Extracted data from 'data' field: {extraction_data}")
            else:
                extraction_data = data
                logger.info(f'Using raw data as extraction data: {extraction_data}')

            # Make sure the data is valid JSON by serializing and deserializing it
            serialized_data = json.dumps(extraction_data, indent=2, ensure_ascii=False)
            # Verify the data can be parsed back into JSON
            json.loads(serialized_data)

            # Log the formatted JSON
            logger.info(f'Extraction tool formatted JSON: {serialized_data}')

            # validate the data adheres to the response schema; an empty schema (dict) results in no validation
            if self.response_schema:
                try:
                    validate(extraction_data, self.response_schema, cls=OAS31Validator)
                except ValidationError as e:
                    logger.error(f'Extraction tool data is invalid: {e}')
                    return ToolResult(error=str(e.message))
                logger.info('Extraction tool data is valid.')
            else:
                logger.info('No response schema provided, skipping validation.')

            # Return the properly formatted data
            return ToolResult(
                output=serialized_data,
                system='Extraction tool successfully processed the data.',
            )
        except json.JSONDecodeError as e:
            error_msg = f'Error processing extraction - invalid JSON: {str(e)}'
            logger.error(error_msg)
            return ToolResult(error=error_msg)
        except Exception as e:
            error_msg = f'Error processing extraction: {str(e)}'
            logger.error(error_msg)
            return ToolResult(error=error_msg)
