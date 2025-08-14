from anthropic.types.beta import BetaToolUnionParam

from server.computer_use.tools.base import BaseAnthropicTool, ToolResult
from server.computer_use.tools.collection import validate_tool_input


class MockTool(BaseAnthropicTool):
    """Mock tool for testing validate_tool_input function."""

    name = 'mock_tool'

    def __call__(
        self, required_param: str, optional_param: str = 'default', **kwargs
    ) -> ToolResult:
        return ToolResult(output=f'Called with {required_param}, {optional_param}')

    def to_params(self) -> BetaToolUnionParam:
        return {
            'name': self.name,
            'description': 'A mock tool for testing',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'required_param': {'type': 'string'},
                    'optional_param': {'type': 'string'},
                },
                'required': ['required_param'],
            },
        }


class MockToolWithSessionId(BaseAnthropicTool):
    """Mock tool with session_id parameter for testing."""

    name = 'mock_tool_with_session'

    def __call__(
        self, session_id: str, param1: str, param2: int = 42, **kwargs
    ) -> ToolResult:
        return ToolResult(
            output=f'Called with session {session_id}, {param1}, {param2}'
        )

    def to_params(self) -> BetaToolUnionParam:
        return {
            'name': self.name,
            'description': 'A mock tool with session_id for testing',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'param1': {'type': 'string'},
                    'param2': {'type': 'integer'},
                },
                'required': ['param1'],
            },
        }


def test_validate_tool_input_valid():
    """Test validate_tool_input with valid input."""
    tool = MockTool()
    tool_input = {'required_param': 'test_value'}

    valid, error = validate_tool_input(tool, tool_input)

    assert valid is True
    assert error is None


def test_validate_tool_input_valid_with_optional():
    """Test validate_tool_input with valid input including optional parameters."""
    tool = MockTool()
    tool_input = {'required_param': 'test_value', 'optional_param': 'custom_value'}

    valid, error = validate_tool_input(tool, tool_input)

    assert valid is True
    assert error is None


def test_validate_tool_input_missing_required():
    """Test validate_tool_input with missing required parameters."""
    tool = MockTool()
    tool_input = {'optional_param': 'custom_value'}  # missing required_param

    valid, error = validate_tool_input(tool, tool_input)

    assert valid is False
    assert error is not None
    assert 'required_param' in error
    assert 'missing required parameters' in error


def test_validate_tool_input_ignores_session_id():
    """Test that validate_tool_input ignores session_id parameter."""
    tool = MockToolWithSessionId()
    tool_input = {'param1': 'test_value'}  # session_id not provided, should be ignored

    valid, error = validate_tool_input(tool, tool_input)

    assert valid is True
    assert error is None


def test_validate_tool_input_multiple_missing_params():
    """Test validate_tool_input with multiple missing required parameters."""

    class MultiParamTool(BaseAnthropicTool):
        name = 'multi_param_tool'

        def __call__(
            self, param1: str, param2: int, param3: str, optional: str = 'default'
        ) -> ToolResult:
            return ToolResult(output='test')

        def to_params(self) -> BetaToolUnionParam:
            return {'name': self.name, 'description': 'test', 'input_schema': {}}

    tool = MultiParamTool()
    tool_input = {'param2': 42}  # missing param1 and param3

    valid, error = validate_tool_input(tool, tool_input)

    assert valid is False
    assert error is not None
    assert 'param1' in error
    assert 'param3' in error
    assert 'missing required parameters' in error
