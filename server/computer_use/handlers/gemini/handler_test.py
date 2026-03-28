import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from server.computer_use.handlers.gemini.handler import GeminiHandler


class FakeGeminiResponse:
    def __init__(self):
        self.model = 'gemini-2.5-flash'
        self.usage_metadata = SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=25,
            cached_content_token_count=10,
        )

    def to_json_dict(self):
        return {
            'model': self.model,
            'candidates': [
                {
                    'content': {
                        'parts': [
                            {'text': 'ok'},
                        ]
                    }
                }
            ],
            'usage_metadata': {
                'prompt_token_count': 100,
                'candidates_token_count': 25,
                'cached_content_token_count': 10,
            },
        }


class FakeGeminiModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeGeminiClient:
    def __init__(self, response):
        self.aio = SimpleNamespace(models=FakeGeminiModels(response))


def test_make_ai_request_returns_normalized_usage_http_response():
    handler = GeminiHandler(model='gemini-2.5-flash', tenant_schema='tenant')
    fake_response = FakeGeminiResponse()
    fake_client = FakeGeminiClient(fake_response)

    response, request, raw_response = asyncio.run(
        handler.make_ai_request(
            client=fake_client,
            messages=[{'role': 'user', 'parts': [{'text': 'hello'}]}],
            system='sys',
            tools=[],
            model='gemini-2.5-flash',
            max_tokens=123,
            temperature=0.0,
        )
    )

    assert response is fake_response
    assert request is not None
    assert request.url.host == 'generativelanguage.googleapis.com'
    assert request.url.path.endswith(':generateContent')
    assert raw_response.status_code == 200
    assert raw_response.json()['usage']['input_tokens'] == 100
    assert raw_response.json()['usage']['output_tokens'] == 25
    assert raw_response.json()['usage']['cache_read_input_tokens'] == 10


def test_make_ai_request_sanitizes_binary_request_parts():
    handler = GeminiHandler(model='gemini-2.5-flash', tenant_schema='tenant')
    fake_client = FakeGeminiClient(FakeGeminiResponse())

    _, request, _ = asyncio.run(
        handler.make_ai_request(
            client=fake_client,
            messages=[
                {
                    'role': 'user',
                    'parts': [
                        {
                            'inline_data': {
                                'mime_type': 'image/png',
                                'data': b'\x89PNG',
                            }
                        }
                    ],
                }
            ],
            system='sys',
            tools=[],
            model='gemini-2.5-flash',
            max_tokens=123,
            temperature=0.0,
        )
    )

    assert request is not None
    request_json = json.loads(request.content.decode('utf-8'))
    assert (
        request_json['contents'][0]['parts'][0]['inline_data']['data']
        == '<binary data: 4 bytes>'
    )


def test_capture_generation_forwards_normalized_usage():
    handler = GeminiHandler(model='gemini-2.5-flash', tenant_schema='tenant')
    response = FakeGeminiResponse()

    with patch(
        'server.computer_use.handlers.gemini.handler.capture_ai_generation'
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
    assert kwargs['ai_input_tokens'] == 100
    assert kwargs['ai_output_tokens'] == 25
    assert kwargs['ai_cache_read_input_tokens'] == 10
