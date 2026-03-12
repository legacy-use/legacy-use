import base64

from server.computer_use.handlers.kimi.message_converter import (
    convert_anthropic_to_kimi_messages,
)


def test_user_text_and_tool_results_are_preserved():
    encoded = base64.b64encode(b'fakepngbytes').decode('ascii')

    messages = [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'Find the value'},
                {
                    'type': 'tool_result',
                    'tool_use_id': 'toolu_1',
                    'error': 'failed once',
                    'is_error': True,
                    'content': [
                        {'type': 'text', 'text': 'retrying'},
                        {
                            'type': 'image',
                            'source': {
                                'type': 'base64',
                                'media_type': 'image/png',
                                'data': encoded,
                            },
                        },
                    ],
                },
            ],
        }
    ]

    converted = convert_anthropic_to_kimi_messages(messages)
    content = converted[0]['content']

    assert {'type': 'text', 'text': 'Find the value'} in content
    assert {'type': 'text', 'text': 'Tool error: failed once'} in content
    assert {'type': 'text', 'text': 'retrying'} in content
    image = next(item for item in content if item.get('type') == 'image_url')
    assert image['image_url']['url'] == f'data:image/png;base64,{encoded}'


def test_assistant_tool_use_history_is_stripped():
    messages = [
        {
            'role': 'assistant',
            'content': [
                {'type': 'text', 'text': '## Thought:\nInspect'},
                {
                    'type': 'tool_use',
                    'id': 'toolu_1',
                    'name': 'computer',
                    'input': {'action': 'left_click'},
                },
            ],
        }
    ]

    converted = convert_anthropic_to_kimi_messages(messages)

    assert converted == [
        {
            'role': 'assistant',
            'content': [{'type': 'text', 'text': '## Thought:\nInspect'}],
        }
    ]
