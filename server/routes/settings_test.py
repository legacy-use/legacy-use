import asyncio

from fastapi import Request

from server.computer_use.config import APIProvider
from server.routes import settings as settings_module


def _request() -> Request:
    return Request({'type': 'http', 'headers': [], 'method': 'GET', 'path': '/'})


def test_get_providers_includes_kimi(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        'get_tenant_from_request',
        lambda request: {'schema': 'tenant'},
    )

    values = {
        'AWS_ACCESS_KEY_ID': 'abcd1234',
        'AWS_SECRET_ACCESS_KEY': 'secret9876',
        'API_PROVIDER': APIProvider.KIMI_BEDROCK.value,
    }
    monkeypatch.setattr(
        settings_module,
        'get_tenant_setting',
        lambda schema, key: values.get(key),
    )

    response = asyncio.run(settings_module.get_providers(_request(), db_tenant=None))

    providers = {provider.provider: provider for provider in response.providers}
    assert APIProvider.KIMI_BEDROCK.value in providers
    assert providers[APIProvider.KIMI_BEDROCK.value].available is True
    assert (
        providers[APIProvider.KIMI_BEDROCK.value].default_model
        == 'moonshotai.kimi-k2.5'
    )
    assert (
        providers[APIProvider.KIMI_BEDROCK.value].credentials['region'] == 'eu-north-1'
    )


def test_get_providers_uses_gpt_5_4_for_openai(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        'get_tenant_from_request',
        lambda request: {'schema': 'tenant'},
    )
    monkeypatch.setattr(
        settings_module,
        'get_tenant_setting',
        lambda schema, key: {
            'API_PROVIDER': APIProvider.OPENAI.value,
            'OPENAI_API_KEY': 'sk-test',
        }.get(key),
    )

    response = asyncio.run(settings_module.get_providers(_request(), db_tenant=None))

    providers = {provider.provider: provider for provider in response.providers}
    assert providers[APIProvider.OPENAI.value].default_model == 'gpt-5.4'


def test_update_provider_settings_sets_fixed_region(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        'get_tenant_from_request',
        lambda request: {'schema': 'tenant'},
    )

    calls = []

    def _set_tenant_setting(schema, key, value):
        calls.append((schema, key, value))

    monkeypatch.setattr(settings_module, 'set_tenant_setting', _set_tenant_setting)

    request = settings_module.UpdateProviderRequest(
        provider=APIProvider.KIMI_BEDROCK.value,
        credentials={
            'access_key_id': 'abc',
            'secret_access_key': 'def',
            'region': 'eu-north-1',
        },
    )

    response = asyncio.run(
        settings_module.update_provider_settings(
            request,
            _request(),
            db_tenant=None,
        )
    )

    assert response['status'] == 'success'
    assert ('tenant', 'AWS_REGION', 'eu-north-1') in calls
