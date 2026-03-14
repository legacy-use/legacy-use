import asyncio

from server.computer_use.config import APIProvider
from server.computer_use.handlers.opencua import handler as opencua_handler_module
from server.computer_use.handlers.opencua.handler import OpenCuaHandler


def test_initialize_client_uses_region_override(monkeypatch):
    captured = {}

    class FakeSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def client(self, service_name, config):
            captured['service_name'] = service_name
            captured['config'] = config
            return object()

    monkeypatch.setattr(opencua_handler_module.aioboto3, 'Session', FakeSession)

    handler = OpenCuaHandler(
        provider=APIProvider.OPENCUA,
        model='opencua-endpoint',
        tenant_schema='tenant',
        region_override='eu-central-1',
    )

    def _tenant_setting(key: str):
        return {
            'AWS_REGION': 'eu-west-1',
            'AWS_ACCESS_KEY_ID': 'access',
            'AWS_SECRET_ACCESS_KEY': 'secret',
        }.get(key)

    handler.tenant_setting = _tenant_setting  # type: ignore[method-assign]

    asyncio.run(handler.initialize_client(api_key=''))

    assert captured['region_name'] == 'eu-central-1'
    assert captured['service_name'] == 'sagemaker-runtime'
