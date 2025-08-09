"""UI not as expected tool for reporting when the UI doesn't match expectations."""

import logging
from typing import Literal

from anthropic.types.beta import BetaToolUnionParam

from .base import BaseAnthropicTool, ToolResult

logger = logging.getLogger('server')


class UINotAsExpectedTool(BaseAnthropicTool):
    """Tool for reporting when the UI doesn't match expectations."""

    name: Literal['ui_not_as_expected'] = 'ui_not_as_expected'

    def to_params(self) -> BetaToolUnionParam:
        return {
            'name': 'ui_not_as_expected',
            'description': "Use this tool when the UI doesn't look as expected or when you're unsure about what you're seeing in the screenshot. Provide a clear explanation of what's different and what you expected to see.",
            'input_schema': {
                'type': 'object',
                'properties': {
                    'reasoning': {
                        'type': 'string',
                        'description': "Detailed explanation of what doesn't match expectations, what you expected to see, and what you're actually seeing in the UI",
                    }
                },
                'required': ['reasoning'],
            },
        }

    async def __call__(self, *, reasoning: str) -> ToolResult:
        """Process the UI not as expected notification."""
        try:
            # Log the reasoning
            logger.info(f'UI not as expected tool called with reasoning: {reasoning}')

            # Return a tool result with the error type to be handled by the system
            # Keep the output simple and clean - avoid redundancy
            return ToolResult(
                output=reasoning,  # Just pass the reasoning directly
                system='UI Mismatch Detected',  # Keep the system message short and clear
                error=None,  # Don't set an error since we handle this specially in the loop
            )
        except Exception as e:
            error_msg = f'Error processing UI not as expected tool: {str(e)}'
            logger.error(error_msg)
            return ToolResult(error=error_msg)
