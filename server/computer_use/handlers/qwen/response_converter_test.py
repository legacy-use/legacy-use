from server.computer_use.handlers.qwen.response_converter import (
    convert_bedrock_to_anthropic_response,
)


def test_tool_use_action_normalized():
    class MockComputerTool:
        width = 1024
        height = 768

    response = {
        'output': {
            'message': {
                'content': [
                    {
                        'toolUse': {
                            'toolUseId': 'toolu_1',
                            'name': 'left_click',
                            'input': {'coordinate': [10, 20]},
                        }
                    }
                ]
            }
        },
        'stopReason': 'tool_use',
    }

    blocks, stop_reason = convert_bedrock_to_anthropic_response(
        response, computer_tool=MockComputerTool()
    )

    assert stop_reason == 'tool_use'
    assert blocks[0]['type'] == 'tool_use'
    assert blocks[0]['name'] == 'computer'
    assert blocks[0]['input']['action'] == 'left_click'
    assert blocks[0]['input']['coordinate'] == (10, 15)


def test_tool_use_action_normalized_thousand_scale():
    class MockComputerTool:
        width = 1024
        height = 768

    response = {
        'output': {
            'message': {
                'content': [
                    {
                        'toolUse': {
                            'toolUseId': 'toolu_1',
                            'name': 'left_click',
                            'input': {'coordinate': [500, 500]},
                        }
                    }
                ]
            }
        },
        'stopReason': 'tool_use',
    }

    blocks, stop_reason = convert_bedrock_to_anthropic_response(
        response, computer_tool=MockComputerTool()
    )

    assert stop_reason == 'tool_use'
    assert blocks[0]['input']['coordinate'] == (512, 384)


def test_extraction_wrapped():
    response = {
        'output': {
            'message': {
                'content': [
                    {
                        'toolUse': {
                            'toolUseId': 'toolu_2',
                            'name': 'extraction',
                            'input': {'name': 'field', 'result': {'value': 1}},
                        }
                    }
                ]
            }
        },
        'stopReason': 'end_turn',
    }

    blocks, stop_reason = convert_bedrock_to_anthropic_response(response)

    assert stop_reason == 'end_turn'
    assert blocks[0]['type'] == 'tool_use'
    assert blocks[0]['input']['data']['name'] == 'field'
    assert blocks[0]['input']['data']['result'] == {'value': 1}
