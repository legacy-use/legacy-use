import json

from server.computer_use.tools.base import ToolResult
from server.computer_use.tools.computer import ComputerTool20251124
from server.computer_use.utils import _make_api_tool_result


def test_make_api_tool_result_stringifies_structured_errors():
    result = ToolResult(error={'detail': [{'msg': 'bad input'}]})

    block = _make_api_tool_result(result, 'toolu_test')

    assert block['is_error'] is True
    assert block['content'][0]['type'] == 'text'
    assert block['content'][0]['text'] == json.dumps(
        {'detail': [{'msg': 'bad input'}]}, ensure_ascii=False
    )


def test_computer_tool_20251124_uses_compatible_runtime_api_type():
    tool = ComputerTool20251124()

    assert tool.runtime_api_type == 'computer_20250124'
