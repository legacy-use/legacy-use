from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, fields, replace
from typing import Any, Dict

from anthropic.types.beta import BetaToolUnionParam


class BaseAnthropicTool(metaclass=ABCMeta):
    """Abstract base class for Anthropic-defined tools."""

    @abstractmethod
    def __call__(self, **kwargs) -> Any:
        """Executes the tool with the given arguments."""
        ...

    @abstractmethod
    def to_params(
        self,
    ) -> BetaToolUnionParam:
        raise NotImplementedError


class BaseOpenAITool(metaclass=ABCMeta):
    """Abstract base class for OpenAI-compatible tools."""

    @abstractmethod
    def __call__(self, **kwargs) -> Any:
        """Executes the tool with the given arguments."""
        ...

    @abstractmethod
    def to_openai_params(self) -> Dict[str, Any]:
        """Convert tool to OpenAI function calling format."""
        raise NotImplementedError


class BaseUniversalTool(BaseAnthropicTool, BaseOpenAITool):
    """Base class for tools that support both Anthropic and OpenAI formats."""

    @abstractmethod
    def to_params(self) -> BetaToolUnionParam:
        """Convert tool to Anthropic format."""
        raise NotImplementedError

    @abstractmethod
    def to_openai_params(self) -> Dict[str, Any]:
        """Convert tool to OpenAI format."""
        raise NotImplementedError


@dataclass(kw_only=True, frozen=True)
class ToolResult:
    """Represents the result of a tool execution."""

    output: str | None = None
    error: str | None = None
    base64_image: str | None = None
    system: str | None = None

    def __bool__(self):
        return any(getattr(self, field.name) for field in fields(self))

    def __add__(self, other: 'ToolResult'):
        def combine_fields(
            field: str | None, other_field: str | None, concatenate: bool = True
        ):
            if field and other_field:
                if concatenate:
                    return field + other_field
                raise ValueError('Cannot combine tool results')
            return field or other_field

        return ToolResult(
            output=combine_fields(self.output, other.output),
            error=combine_fields(self.error, other.error),
            base64_image=combine_fields(self.base64_image, other.base64_image, False),
            system=combine_fields(self.system, other.system),
        )

    def replace(self, **kwargs):
        """Returns a new ToolResult with the given fields replaced."""
        return replace(self, **kwargs)


class CLIResult(ToolResult):
    """A ToolResult that can be rendered as a CLI output."""


class ToolFailure(ToolResult):
    """A ToolResult that represents a failure."""


class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message


def anthropic_to_openai_tool(anthropic_tool: BetaToolUnionParam) -> Dict[str, Any]:
    """Convert Anthropic tool format to OpenAI function calling format."""
    if (
        anthropic_tool.get('type') == 'computer_20241022'
        or anthropic_tool.get('type') == 'computer_20250124'
    ):
        return {
            'type': 'function',
            'function': {
                'name': anthropic_tool['name'],
                'description': 'A tool that allows the agent to interact with the screen, keyboard, and mouse of a remote computer. The tool takes a screenshot after each action and returns the screenshot as a base64 encoded image.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'action': {
                            'type': 'string',
                            'enum': [
                                'key',
                                'type',
                                'mouse_move',
                                'left_click',
                                'left_click_drag',
                                'right_click',
                                'middle_click',
                                'double_click',
                                'screenshot',
                                'cursor_position',
                                'left_mouse_down',
                                'left_mouse_up',
                                'scroll',
                                'hold_key',
                                'wait',
                                'triple_click',
                            ],
                            'description': 'The action to perform',
                        },
                        'text': {
                            'type': 'string',
                            'description': 'Text to type (for type action)',
                        },
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                            'description': 'Coordinate [x, y] for mouse actions',
                        },
                        'scroll_direction': {
                            'type': 'string',
                            'enum': ['up', 'down', 'left', 'right'],
                            'description': 'Direction to scroll',
                        },
                        'scroll_amount': {
                            'type': 'integer',
                            'description': 'Amount to scroll',
                        },
                        'duration': {
                            'type': 'number',
                            'description': 'Duration for actions that support it',
                        },
                        'key': {
                            'type': 'string',
                            'description': 'Key to press (for key actions)',
                        },
                    },
                    'required': ['action'],
                },
            },
        }
    elif anthropic_tool.get('name') == 'extraction':
        return {
            'type': 'function',
            'function': {
                'name': 'extraction',
                'description': "Use this tool to return the final JSON result when you've found the information requested by the user.",
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'data': {
                            'type': 'object',
                            'description': 'The extracted data to return as JSON',
                        }
                    },
                    'required': ['data'],
                },
            },
        }
    elif anthropic_tool.get('name') == 'ui_not_as_expected':
        return {
            'type': 'function',
            'function': {
                'name': 'ui_not_as_expected',
                'description': "Use this tool when the UI doesn't look as expected or when you're unsure about what you're seeing in the screenshot. Provide a clear explanation of what's different and what you expected to see.",
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'reasoning': {
                            'type': 'string',
                            'description': "Detailed explanation of what doesn't match expectations, what you expected to see, and what you're actually seeing in the UI",
                        }
                    },
                    'required': ['reasoning'],
                },
            },
        }
    else:
        # Generic conversion for other tools
        return {
            'type': 'function',
            'function': {
                'name': anthropic_tool.get('name', 'unknown'),
                'description': anthropic_tool.get('description', ''),
                'parameters': anthropic_tool.get('input_schema', {}),
            },
        }


def openai_to_anthropic_tool_result(
    openai_result: Dict[str, Any], tool_call_id: str
) -> Dict[str, Any]:
    """Convert OpenAI tool result to Anthropic format."""
    return {
        'type': 'tool_result',
        'tool_use_id': tool_call_id,
        'content': [{'type': 'text', 'text': str(openai_result)}],
    }
