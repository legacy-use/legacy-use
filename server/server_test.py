from fastapi.testclient import TestClient

from .server import app

client = TestClient(app, base_url='http://tenant-default.local.legacy-use.com')


def test_main_no_api_key():
    response = client.get('/')
    assert response.status_code == 401
    assert response.json() == {'detail': 'API key is missing'}


def test_main_wrong_api_key():
    response = client.get('/', headers={'X-API-Key': 'wrong_api_key'})
    assert response.status_code == 401
    assert response.json() == {'detail': 'Invalid API Key'}
