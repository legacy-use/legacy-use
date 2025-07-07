"""Collection classes for managing multiple tools."""

from typing import Any, Dict, List

from anthropic.types.beta import BetaToolUnionParam

from .base import (
    BaseAnthropicTool,
    BaseUniversalTool,
    ToolError,
    ToolFailure,
    ToolResult,
    anthropic_to_openai_tool,
)
from .computer import BaseComputerTool


class ToolCollection:
    """A collection of anthropic-defined tools."""

    def __init__(self, *tools: BaseAnthropicTool):
        self.tools = tools
        self.tool_map = {tool.to_params()['name']: tool for tool in tools}

    def to_params(
        self,
    ) -> list[BetaToolUnionParam]:
        return [tool.to_params() for tool in self.tools]

    def to_openai_params(self) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI function calling format."""
        openai_tools = []
        for tool in self.tools:
            if isinstance(tool, BaseUniversalTool):
                # Tool supports both formats
                openai_tools.append(tool.to_openai_params())
            else:
                # Convert from Anthropic format
                anthropic_params = tool.to_params()
                openai_tools.append(anthropic_to_openai_tool(anthropic_params))
        return openai_tools

    async def run(
        self, *, name: str, tool_input: dict[str, Any], session_id: str
    ) -> ToolResult:
        tool = self.tool_map.get(name)
        if not tool:
            return ToolFailure(error=f'Tool {name} is invalid')
        try:
            if isinstance(tool, BaseComputerTool):
                return await tool(session_id=session_id, **tool_input)
            else:
                return await tool(**tool_input)
        except ToolError as e:
            return ToolFailure(error=e.message)
