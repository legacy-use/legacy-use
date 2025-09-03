import logging
from typing import Any, Dict, Literal

from anthropic.types.beta import BetaToolUnionParam

from .base import BaseAnthropicTool, ToolError, ToolResult

logger = logging.getLogger('server')


class CustomActionTool(BaseAnthropicTool):
    name: Literal['custom_action'] = 'custom_action'
    custom_actions: Dict[str, Any]

    def __init__(
        self,
        custom_actions: Dict[str, Any] | None = None,
        input_parameters: Dict[str, Any] | None = None,
    ):
        super().__init__()
        self.custom_actions = custom_actions or {}
        # all custom action names to lowercase
        self.custom_actions = {k.lower(): v for k, v in self.custom_actions.items()}
        self.input_parameters = input_parameters

    def _get_action(self, action_name: str) -> Dict[str, Any]:
        return self.custom_actions.get(action_name.lower(), None)

    def _inject_input_parameters(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        if not self.input_parameters:
            logger.info(
                f'No input parameters found in custom action tool: {self.input_parameters}'
            )
            return tool
        if not tool['parameters']:
            logger.info(f'No parameters found in tool: {tool}')
            return tool
        # if in any parameter of the action is {{parameter_name}}, replace it with the value of the parameter_name from the input_parameters
        has_text = 'text' in tool['parameters']
        has_placeholder = has_text and '{{' in tool['parameters'].get('text')
        if not has_placeholder:
            logger.info(
                f'No placeholder found in text: {tool["parameters"].get("text")}'
            )
            return tool

        for param_name, param_value in self.input_parameters.items():
            placeholder_patterns = '{{' + param_name + '}}'  # {{param_name}
            if placeholder_patterns in tool['parameters'].get('text'):
                logger.info(
                    f'Replacing placeholder: {placeholder_patterns} with {param_value}'
                )
                tool['parameters']['text'] = tool['parameters']['text'].replace(
                    placeholder_patterns, str(param_value)
                )
            else:
                logger.info(
                    f'Placeholder not found in text: {tool["parameters"].get("text")}'
                )

        return tool

    def to_params(self) -> BetaToolUnionParam:
        return {
            'name': 'custom_action',
            'description': 'Use this tool when you need to perform a custom action.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'action_name': {
                        'type': 'string',
                        # generating enum dynamically, based on the given custom_actions
                        'enum': list(self.custom_actions.keys())
                        if self.custom_actions
                        else [],
                        'description': 'The name of the custom action to perform',
                    }
                },
                'required': ['action_name'],
            },
        }

    async def __call__(self, **kwargs) -> ToolResult | ToolError:
        """Process the custom action."""
        try:
            action_name = kwargs.get('action_name')
            tool_collection = kwargs.get('tool_collection')

            if not action_name:
                return ToolError('Missing required parameter: action_name')
            if not tool_collection:
                return ToolError('Missing required parameter: tool_collection')

            # Log the reasoning
            logger.info(
                f'Custom action tool called with action_name: {action_name}, input_parameters: {self.input_parameters}'
            )

            action = self._get_action(action_name)
            if not action:
                return ToolError(
                    f'Custom action {action_name} not found',
                )

            # run all actions
            for tool_action in action['tools']:
                logger.info(f'Running action: {tool_action}')
                tool_action = self._inject_input_parameters(tool_action)
                result = await tool_collection.run(
                    name=tool_action['name'],
                    tool_input=tool_action['parameters'],
                    session_id=kwargs.get('session_id', None),
                    session=kwargs.get('session', None),
                )
                if result.error:
                    return ToolError(result.error)

            # screenshot tool to return screenshot as final result
            return await tool_collection.run(
                name='computer',
                tool_input={'action': 'screenshot'},
                session_id=kwargs.get('session_id', None),
                session=kwargs.get('session', None),
            )
        except Exception as e:
            error_msg = f'Error processing custom action tool: {str(e)}'
            logger.error(error_msg)
            return ToolError(error_msg)
