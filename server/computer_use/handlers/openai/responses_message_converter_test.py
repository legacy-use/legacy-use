import base64

import pytest

from server.computer_use.handlers.openai.responses_message_converter import (
    build_openai_responses_request,
    make_openai_computer_tool_use_id,
    make_openai_function_tool_use_id,
)


def test_initial_request_uses_message_input():
    request = build_openai_responses_request(
        messages=[{'role': 'user', 'content': 'Open the site and extract the title.'}],
        provider_state=None,
    )

    assert request.previous_response_id is None
    assert request.input_items == [
        {
            'role': 'user',
            'content': [
                {
                    'type': 'input_text',
                    'text': 'Open the site and extract the title.',
                }
            ],
        }
    ]


def test_follow_up_groups_computer_tool_results_and_acknowledges_safety_checks():
    image_data = base64.b64encode(b'png-bytes').decode('ascii')

    request = build_openai_responses_request(
        messages=[
            {
                'role': 'assistant',
                'content': [
                    {
                        'type': 'tool_use',
                        'id': make_openai_computer_tool_use_id('call_123', 0),
                        'name': 'computer',
                        'input': {'action': 'left_click', 'coordinate': (10, 20)},
                    }
                ],
            },
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': make_openai_computer_tool_use_id('call_123', 0),
                        'content': [{'type': 'text', 'text': 'clicked'}],
                    }
                ],
            },
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': make_openai_computer_tool_use_id('call_123', 1),
                        'content': [
                            {'type': 'text', 'text': 'screenshot'},
                            {
                                'type': 'image',
                                'source': {
                                    'type': 'base64',
                                    'media_type': 'image/png',
                                    'data': image_data,
                                },
                            },
                        ],
                    }
                ],
            },
        ],
        provider_state={
            'last_response_id': 'resp_123',
            'pending_safety_checks': [{'id': 'safe_1'}],
        },
    )

    assert request.previous_response_id == 'resp_123'
    assert request.input_items == [
        {
            'type': 'computer_call_output',
            'call_id': 'call_123',
            'output': {
                'type': 'computer_screenshot',
                'image_url': f'data:image/png;base64,{image_data}',
                'detail': 'original',
            },
            'acknowledged_safety_checks': [{'id': 'safe_1'}],
        }
    ]
    assert request.provider_state == {'last_response_id': 'resp_123'}


def test_follow_up_converts_function_results():
    request = build_openai_responses_request(
        messages=[
            {'role': 'assistant', 'content': []},
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': make_openai_function_tool_use_id('fn_1'),
                        'content': [{'type': 'text', 'text': '{"value": 1}'}],
                    }
                ],
            },
        ],
        provider_state={'last_response_id': 'resp_456'},
    )

    assert request.input_items == [
        {
            'type': 'function_call_output',
            'call_id': 'fn_1',
            'output': '{"value": 1}',
        }
    ]


def test_follow_up_requires_last_response_id():
    with pytest.raises(
        ValueError,
        match='OpenAI Responses job cannot resume without provider_state.last_response_id',
    ):
        build_openai_responses_request(
            messages=[{'role': 'assistant', 'content': []}],
            provider_state={},
        )
