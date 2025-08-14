"""Collection classes for managing multiple tools."""

import inspect
from typing import Any, Dict

from anthropic.types.beta import BetaToolUnionParam

from server.computer_use.logging import logger

from .base import (
    BaseAnthropicTool,
    ToolError,
    ToolFailure,
    ToolResult,
)
from .computer import BaseComputerTool


def validate_tool_input(
    tool: BaseAnthropicTool, tool_input: dict[str, Any]
) -> tuple[bool, str | None]:
    """Validate tool input against the tool's input schema."""

    input_params = set(tool_input.keys())

    func = tool.__call__
    signature = inspect.signature(func)
    expected_params = signature.parameters.items()

    required_params = set()

    for param, value in expected_params:
        # skip self, session_id, kwargs
        if param in {'self', 'session_id', 'kwargs'}:
            continue
        if value.default is inspect.Parameter.empty:
            required_params.add(param)
    missing_params = required_params - input_params

    if missing_params:
        logger.error(
            f'Tool {tool.name} input is missing required parameters: {missing_params}'
        )
        return (
            False,
            f'Tool {tool.name} input is missing required parameters: {missing_params}',
        )

    return True, None


class ToolCollection:
    """A collection of anthropic-defined tools."""

    def __init__(self, *tools: BaseAnthropicTool):
        self.tools = tools
        self.tool_map = {tool.to_params()['name']: tool for tool in tools}

    def to_params(
        self,
    ) -> list[BetaToolUnionParam]:
        return [tool.to_params() for tool in self.tools]

    async def run(
        self,
        *,
        name: str,
        tool_input: dict[str, Any],
        session_id: str,
        session: Dict[str, Any] | None = None,
    ) -> ToolResult:
        tool = self.tool_map.get(name)
        if not tool:
            return ToolFailure(error=f'Tool {name} is invalid')

        # Validate tool input
        valid, error = validate_tool_input(tool, tool_input)

        if not valid:
            # Create tool result prompting the AI to fix the input
            return ToolResult(
                output=f'The tool {name} failed! Reason: "{error}". Please fix the input and try again.',
            )

        try:
            if isinstance(tool, BaseComputerTool):
                return await tool(session_id=session_id, session=session, **tool_input)
            else:
                return await tool(**tool_input)
        except ToolError as e:
            return ToolFailure(error=e.message)
