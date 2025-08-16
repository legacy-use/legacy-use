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

    def internal_spec(self) -> dict:
        """Provider-agnostic spec for this tool (actions, params, docs).

        Default implementation derives a minimal spec from to_params().
        Rich tools (e.g., computer) should override this to include
        actions, per-action params, normalization rules, and options.
        """
        params = self.to_params()
        # Cope with SDK objects (e.g., pydantic/dataclass) and plain dicts
        getter = getattr(params, 'get', None)
        if callable(getter):
            get = getter  # dict-like
        else:

            def get(k, default=None):
                return getattr(params, k, default)  # attr-like

        return {
            'name': get('name'),
            'description': get('description'),
            'input_schema': get('input_schema')
            or {
                'type': 'object',
                'properties': {},
            },
            'options': {},
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
