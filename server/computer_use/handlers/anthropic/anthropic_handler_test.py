import asyncio

from server.computer_use.config import APIProvider
from server.computer_use.handlers.anthropic import handler as anthropic_handler_module
from server.computer_use.handlers.anthropic.handler import AnthropicHandler


def test_bedrock_region_override_precedes_tenant_setting(monkeypatch):
    captured = {}

    class FakeAsyncAnthropicBedrock:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        anthropic_handler_module, 'AsyncAnthropicBedrock', FakeAsyncAnthropicBedrock
    )
    monkeypatch.setattr(
        anthropic_handler_module.instructor,
        'from_anthropic',
        lambda client: client,
    )

    handler = AnthropicHandler(
        provider=APIProvider.BEDROCK,
        model='eu.anthropic.claude-sonnet-4-20250514-v1:0',
        tenant_schema='tenant',
        region_override='us-west-2',
    )

    def _tenant_setting(key: str):
        return {
            'AWS_REGION': 'eu-west-1',
            'AWS_ACCESS_KEY_ID': 'access',
            'AWS_SECRET_ACCESS_KEY': 'secret',
            'AWS_SESSION_TOKEN': None,
        }.get(key)

    handler.tenant_setting = _tenant_setting  # type: ignore[method-assign]

    asyncio.run(handler.initialize_client(api_key=''))

    assert captured['aws_region'] == 'us-west-2'
