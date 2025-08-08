from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, fields, replace
from typing import Any

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

    def to_openai_tool(self) -> dict:
        """Return this tool in OpenAI function tool schema.

        Default implementation converts the Anthropic input_schema (if any)
        into an OpenAI function definition. Tools that do not expose an
        input_schema via to_params (e.g., computer tool) should override this.
        """
        params = self.to_params()
        name = params.get('name')  # type: ignore[arg-type]
        description = params.get('description') or f'Tool: {name}'  # type: ignore[assignment]
        input_schema = params.get('input_schema')  # type: ignore[assignment]

        if not input_schema:
            # If a tool has no input schema, provide an empty object schema by default
            input_schema = {
                'type': 'object',
                'properties': {},
            }

        return {
            'type': 'function',
            'function': {
                'name': name,
                'description': description,
                'parameters': input_schema,
            },
        }


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
