import asyncio
import json
from unittest.mock import patch

from anthropic.types.beta import BetaMessageParam

from server.computer_use.handlers.kimi.handler import KimiBedrockHandler
from server.computer_use.tools.collection import ToolCollection
from server.computer_use.tools.computer import ComputerTool20250124
from server.computer_use.tools.custom_action import CustomActionTool


class FakeBody:
    def __init__(self, payload: bytes):
        self._payload = payload

    async def read(self):
        return self._payload


class FakeBedrockClient:
    def __init__(self, response):
        self.response = response
        self.payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def invoke_model(self, **payload):
        self.payload = payload
        return {
            'body': FakeBody(json.dumps(self.response).encode('utf-8')),
            'contentType': 'application/json',
        }


def test_prepare_tools_populates_system_context():
    handler = KimiBedrockHandler(model='moonshotai.kimi-k2.5', tenant_schema='tenant')
    tools = ToolCollection(
        ComputerTool20250124(),
        CustomActionTool(custom_actions={'login': {'tools': []}}),
    )

    handler.prepare_tools(tools)
    system_prompt = handler.prepare_system('ignored')

    assert handler._computer_options['display_width_px'] == 1024
    assert handler._custom_action_names == ['login']
    assert 'login' in system_prompt


def test_kimi_clamps_image_history_to_one():
    handler = KimiBedrockHandler(
        model='moonshotai.kimi-k2.5',
        tenant_schema='tenant',
        only_n_most_recent_images=3,
    )

    assert handler.only_n_most_recent_images == 1


def test_make_ai_request_uses_invoke_model():
    handler = KimiBedrockHandler(model='moonshotai.kimi-k2.5', tenant_schema='tenant')
    fake_client = FakeBedrockClient(
        {
            'choices': [{'message': {'content': 'ok'}}],
            'usage': {
                'prompt_tokens': 100,
                'completion_tokens': 25,
                'prompt_tokens_details': {'cached_tokens': 10},
            },
        }
    )

    response, request, raw_response = asyncio.run(
        handler.make_ai_request(
            client=fake_client,
            messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'hello'}]}],
            system='sys',
            tools=[],
            model='moonshotai.kimi-k2.5',
            max_tokens=123,
            temperature=0.0,
        )
    )

    assert fake_client.payload['modelId'] == 'moonshotai.kimi-k2.5'
    request_json = json.loads(fake_client.payload['body'].decode('utf-8'))
    assert request_json['messages'][0] == {'role': 'system', 'content': 'sys'}
    assert request_json['messages'][1]['role'] == 'user'
    assert request_json['max_tokens'] == 123
    assert request.url.host == 'bedrock-runtime.eu-north-1.amazonaws.com'
    assert request.url.path.endswith('/invoke')
    assert raw_response.status_code == 200
    assert response['choices'][0]['message']['content'] == 'ok'
    assert raw_response.json()['usage']['input_tokens'] == 100
    assert raw_response.json()['usage']['output_tokens'] == 25
    assert raw_response.json()['usage']['cache_read_input_tokens'] == 10


def test_capture_generation_forwards_normalized_usage():
    handler = KimiBedrockHandler(model='moonshotai.kimi-k2.5', tenant_schema='tenant')
    response = {
        'model': 'moonshotai.kimi-k2.5',
        'usage': {
            'prompt_tokens': 120,
            'completion_tokens': 34,
            'prompt_tokens_details': {'cached_tokens': 12},
        },
    }

    with patch(
        'server.computer_use.handlers.kimi.handler.capture_ai_generation'
    ) as capture:
        handler._capture_generation(
            response=response,
            job_id='job-1',
            iteration_count=2,
            temperature=0.0,
            max_tokens=256,
        )

    capture.assert_called_once()
    kwargs = capture.call_args.kwargs
    assert kwargs['ai_input_tokens'] == 120
    assert kwargs['ai_output_tokens'] == 34
    assert kwargs['ai_cache_read_input_tokens'] == 12


def test_initialize_client_requires_credentials():
    handler = KimiBedrockHandler(model='moonshotai.kimi-k2.5', tenant_schema='tenant')

    def _tenant_setting(_key: str):
        return None

    handler.tenant_setting = _tenant_setting  # type: ignore[method-assign]

    try:
        asyncio.run(handler.initialize_client(api_key=''))
    except ValueError as exc:
        assert 'AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required' in str(exc)
    else:
        raise AssertionError('Expected initialize_client to raise ValueError')


def test_execute_terminates_with_ui_not_as_expected_after_retry_exhaustion():
    handler = KimiBedrockHandler(
        model='moonshotai.kimi-k2.5',
        tenant_schema='tenant',
        max_retries=0,
    )
    fake_client = FakeBedrockClient(
        {'choices': [{'message': {'content': 'I will think but not emit code.'}}]}
    )
    tools = ToolCollection(ComputerTool20250124())
    messages = [
        BetaMessageParam(
            role='assistant',
            content=[
                {
                    'type': 'tool_use',
                    'id': 'toolu_retry_screenshot_0',
                    'name': 'computer',
                    'input': {'action': 'screenshot'},
                }
            ],
        ),
        BetaMessageParam(
            role='user',
            content=[
                {'type': 'text', 'text': 'do the thing'},
                {
                    'type': 'tool_result',
                    'tool_use_id': 'toolu_prev',
                    'content': [
                        {
                            'type': 'image',
                            'source': {
                                'type': 'base64',
                                'media_type': 'image/png',
                                'data': 'ZmFrZQ==',
                            },
                        }
                    ],
                },
            ],
        ),
    ]

    content_blocks, stop_reason, _, _ = asyncio.run(
        handler.execute(
            job_id='job-1',
            iteration_count=1,
            client=fake_client,
            messages=messages,
            system='ignored',
            tools=tools,
            model='moonshotai.kimi-k2.5',
            max_tokens=256,
            temperature=0.0,
        )
    )

    assert stop_reason == 'end_turn'
    assert content_blocks[-1]['type'] == 'tool_use'
    assert content_blocks[-1]['name'] == 'ui_not_as_expected'
    assert (
        'did not include a supported tool action'
        in content_blocks[-1]['input']['reasoning']
    )
