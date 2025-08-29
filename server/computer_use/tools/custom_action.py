import logging
from typing import Literal

from anthropic.types.beta import BetaToolUnionParam

from server.computer_use.tools.collection import ToolCollection

from .base import BaseAnthropicTool, ToolResult

logger = logging.getLogger('server')


class CustomActionTool(BaseAnthropicTool):
    name: Literal['custom_action'] = 'custom_action'

    def to_params(self) -> BetaToolUnionParam:
        return {
            'name': 'custom_action',
            'description': 'Use this tool when you need to perform a custom action.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'action_id': {
                        'type': 'string',
                        'description': 'The action id of the custom action',
                    }
                    # api_name and parameters are are handled in the sampling_loop.py and are not required to be passed by the model
                },
                'required': ['action_id'],
            },
        }

    async def __call__(
        self, action_id: str, api_name: str, tool_collection: ToolCollection, **kwargs
    ) -> ToolResult:
        """Process the custom action."""
        try:
            # Log the reasoning
            logger.info(
                f'Custom action tool called with action_id: {action_id} api_name: {api_name}'
            )
            logger.info(f'Session: {kwargs.get("session", None)}')
            logger.info(f'Session ID: {kwargs.get("session_id", None)}')

            # TODO: handle dynamic parameter input
            # TODO: How to handle sleep times?

            # get all actions by api_name and action_id
            actions = [
                {
                    'name': 'computer',
                    'parameters': {
                        'action': 'left_click',
                        'coordinate': [100, 100],
                    },
                },
                {
                    'name': 'computer',
                    'parameters': {'action': 'key', 'text': 'Super_L'},
                },
                {
                    'name': 'computer',
                    'parameters': {'action': 'type', 'text': 'notepad'},
                },
                {
                    'name': 'computer',
                    'parameters': {'action': 'key', 'text': 'Return'},
                },
                {
                    'name': 'computer',
                    'parameters': {'action': 'type', 'text': 'helloworld'},
                },
            ]

            results = []

            # run all actions
            for action in actions:
                logger.info(f'Running action: {action}')
                result = await tool_collection.run(
                    name=action['name'],
                    tool_input=action['parameters'],
                    session_id=kwargs.get('session_id', None),
                    session=kwargs.get('session', None),
                )
                logger.info('Action result')
                results.append(result)
                if result.error:
                    return ToolResult(error=result.error)

            # if all went fine return success (and screenshot?)
            return ToolResult(output='Success')
        except Exception as e:
            error_msg = f'Error processing UI not as expected tool: {str(e)}'
            logger.error(error_msg)
            return ToolResult(error=error_msg)
