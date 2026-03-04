from server.computer_use.handlers.kimi.response_converter import (
    convert_kimi_to_anthropic_response,
)


def test_compliant_response_yields_text_and_tool_use():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nInspect the button\n## Action:\nClick the button\n## Code:\n```python\npyautogui.click(x=10, y=20)\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'tool_use'
    assert blocks[0]['type'] == 'text'
    assert '## Thought:' in blocks[0]['text']
    assert blocks[1]['type'] == 'tool_use'
    assert blocks[1]['name'] == 'computer'
    assert blocks[1]['input']['action'] == 'left_click'


def test_terminate_response_is_end_turn():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nDone\n## Action:\nReturn result\n## Code:\n```python\ncomputer.terminate(status="success", data="{\\"done\\": true}")\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'end_turn'
    assert blocks[1]['type'] == 'tool_use'
    assert blocks[1]['name'] == 'extraction'


def test_malformed_response_returns_text_only():
    response = {
        'choices': [
            {'message': {'content': 'I am not following the requested format.'}}
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'end_turn'
    assert len(blocks) == 1
    assert blocks[0]['type'] == 'text'
