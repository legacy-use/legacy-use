from server.computer_use.config import get_tool_version


def test_get_tool_version_uses_latest_computer_use_for_claude_46_and_opus_45():
    assert get_tool_version('claude-sonnet-4-6') == 'computer_use_20251124'
    assert get_tool_version('claude-opus-4-6') == 'computer_use_20251124'
    assert get_tool_version('anthropic.claude-opus-4-5-v1:0') == 'computer_use_20251124'


def test_get_tool_version_keeps_20250124_for_older_models():
    assert get_tool_version('claude-sonnet-4-20250514') == 'computer_use_20250124'
    assert get_tool_version('claude-sonnet-4-5') == 'computer_use_20250124'
