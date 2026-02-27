import asyncio

from server.computer_use.handlers.kimi.handler import KimiBedrockHandler
from server.computer_use.tools.collection import ToolCollection
from server.computer_use.tools.computer import ComputerTool20250124
from server.computer_use.tools.custom_action import CustomActionTool


class FakeBedrockClient:
    def __init__(self, response):
        self.response = response
        self.payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def converse(self, **payload):
        self.payload = payload
        return self.response


def test_prepare_tools_populates_system_context():
    handler = KimiBedrockHandler(
        model='moonshotai.kimi-k2-5-20250929-v1:0', tenant_schema='tenant'
    )
    tools = ToolCollection(
        ComputerTool20250124(),
        CustomActionTool(custom_actions={'login': {'tools': []}}),
    )

    handler.prepare_tools(tools)
    system_blocks = handler.prepare_system('ignored')

    assert handler._computer_options['display_width_px'] == 1024
    assert handler._custom_action_names == ['login']
    assert 'login' in system_blocks[0]['text']


def test_make_ai_request_omits_tool_config():
    handler = KimiBedrockHandler(
        model='moonshotai.kimi-k2-5-20250929-v1:0', tenant_schema='tenant'
    )
    fake_client = FakeBedrockClient(
        {'output': {'message': {'content': [{'text': 'ok'}]}}, 'usage': {}}
    )

    response, request, raw_response = asyncio.run(
        handler.make_ai_request(
            client=fake_client,
            messages=[{'role': 'user', 'content': [{'text': 'hello'}]}],
            system=[{'text': 'sys'}],
            tools=[],
            model='moonshotai.kimi-k2-5-20250929-v1:0',
            max_tokens=123,
            temperature=0.0,
        )
    )

    assert 'toolConfig' not in fake_client.payload
    assert fake_client.payload['modelId'] == 'moonshotai.kimi-k2-5-20250929-v1:0'
    assert request.url.host == 'bedrock-runtime.eu-west-2.amazonaws.com'
    assert raw_response.status_code == 200
    assert response['output']['message']['content'][0]['text'] == 'ok'


def test_initialize_client_requires_credentials():
    handler = KimiBedrockHandler(
        model='moonshotai.kimi-k2-5-20250929-v1:0', tenant_schema='tenant'
    )

    def _tenant_setting(_key: str):
        return None

    handler.tenant_setting = _tenant_setting  # type: ignore[method-assign]

    try:
        asyncio.run(handler.initialize_client(api_key=''))
    except ValueError as exc:
        assert 'AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required' in str(exc)
    else:
        raise AssertionError('Expected initialize_client to raise ValueError')
