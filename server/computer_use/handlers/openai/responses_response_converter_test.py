from server.computer_use.handlers.openai.responses_response_converter import (
    convert_openai_responses_to_anthropic_response,
)


def test_text_only_response_converts_to_end_turn():
    response = {
        'id': 'resp_text',
        'status': 'completed',
        'output': [
            {
                'type': 'message',
                'content': [{'type': 'output_text', 'text': 'All done.'}],
            }
        ],
    }

    blocks, stop_reason, provider_state = (
        convert_openai_responses_to_anthropic_response(response)
    )

    assert stop_reason == 'end_turn'
    assert blocks == [{'type': 'text', 'text': 'All done.'}]
    assert provider_state == {
        'last_response_id': 'resp_text',
        'model_family': 'openai_responses_computer',
    }


def test_computer_call_batches_actions_and_adds_synthetic_screenshot():
    response = {
        'id': 'resp_tools',
        'status': 'completed',
        'output': [
            {
                'type': 'computer_call',
                'call_id': 'call_abc',
                'actions': [
                    {'type': 'click', 'x': 10, 'y': 20},
                    {'type': 'type', 'text': 'hello'},
                ],
            }
        ],
    }

    blocks, stop_reason, _ = convert_openai_responses_to_anthropic_response(response)

    assert stop_reason == 'tool_use'
    assert [block['input']['action'] for block in blocks] == [
        'left_click',
        'type',
        'screenshot',
    ]
    assert blocks[0]['id'] == 'openai_computer:call_abc:0'
    assert blocks[1]['id'] == 'openai_computer:call_abc:1'
    assert blocks[2]['id'] == 'openai_computer:call_abc:2'
    assert blocks[0]['input']['coordinate'] == (10, 20)
    assert blocks[1]['input']['text'] == 'hello'


def test_mixed_computer_and_function_calls_preserve_ids_and_safety_state():
    response = {
        'id': 'resp_mix',
        'status': 'completed',
        'output': [
            {
                'type': 'function_call',
                'call_id': 'fn_1',
                'name': 'extraction',
                'arguments': '{"data": {"value": 42}}',
            },
            {
                'type': 'computer_call',
                'call_id': 'call_mix',
                'pending_safety_checks': [{'id': 'safe_1'}],
                'actions': [{'type': 'keypress', 'keys': ['CTRL', 'L']}],
            },
        ],
    }

    blocks, stop_reason, provider_state = (
        convert_openai_responses_to_anthropic_response(response)
    )

    assert stop_reason == 'tool_use'
    assert blocks[0]['id'] == 'openai_function:fn_1'
    assert blocks[0]['name'] == 'extraction'
    assert blocks[1]['name'] == 'computer'
    assert blocks[1]['input']['action'] == 'key'
    assert blocks[1]['input']['text'] == 'ctrl+L'
    assert provider_state['pending_safety_checks'] == [{'id': 'safe_1'}]
