import asyncio
import json

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


def test_make_ai_request_uses_invoke_model():
    handler = KimiBedrockHandler(model='moonshotai.kimi-k2.5', tenant_schema='tenant')
    fake_client = FakeBedrockClient({'choices': [{'message': {'content': 'ok'}}]})

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
