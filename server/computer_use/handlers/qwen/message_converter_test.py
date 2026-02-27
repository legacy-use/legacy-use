import base64

from server.computer_use.handlers.qwen.message_converter import (
    convert_anthropic_to_bedrock_messages,
)


def test_tool_result_with_image_converted():
    image_bytes = b'fakepngbytes'
    encoded = base64.b64encode(image_bytes).decode('ascii')

    messages = [
        {
            'role': 'user',
            'content': [
                {
                    'type': 'tool_result',
                    'tool_use_id': 'toolu_1',
                    'content': [
                        {'type': 'text', 'text': 'done'},
                        {
                            'type': 'image',
                            'source': {
                                'type': 'base64',
                                'media_type': 'image/png',
                                'data': encoded,
                            },
                        },
                    ],
                }
            ],
        }
    ]

    bedrock_messages = convert_anthropic_to_bedrock_messages(messages)

    assert bedrock_messages[0]['role'] == 'user'
    content = bedrock_messages[0]['content']

    tool_result = next(item['toolResult'] for item in content if 'toolResult' in item)
    assert tool_result['toolUseId'] == 'toolu_1'
    assert tool_result['status'] == 'success'
    assert {'text': 'done'} in tool_result['content']

    image = next(item['image'] for item in content if 'image' in item)
    assert image['source']['bytes'] == image_bytes


def test_tool_use_converted():
    messages = [
        {
            'role': 'assistant',
            'content': [
                {
                    'type': 'tool_use',
                    'id': 'toolu_abc',
                    'name': 'search',
                    'input': {'q': 'hello'},
                }
            ],
        }
    ]

    bedrock_messages = convert_anthropic_to_bedrock_messages(messages)

    tool_use = bedrock_messages[0]['content'][0]['toolUse']
    assert tool_use['toolUseId'] == 'toolu_abc'
    assert tool_use['name'] == 'search'
    assert tool_use['input'] == {'q': 'hello'}
