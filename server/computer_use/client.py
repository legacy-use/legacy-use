from typing import Any, Iterable
from anthropic.types.beta import BetaMessageParam, BetaTextBlockParam
from anthropic import APIStatusError
import httpx
from server.settings import settings
from server.computer_use.logging import logger


class ContentBlockWrapper:
    """Wrapper for individual content blocks to provide Pydantic model interface"""

    def __init__(self, block_dict: dict):
        self._dict = block_dict

    def model_dump(self):
        """Provide model_dump method expected by _response_to_params"""
        return self._dict

    @property
    def text(self):
        """Provide .text attribute for text blocks"""
        return self._dict.get('text')

    @property
    def type(self):
        """Provide .type attribute"""
        return self._dict.get('type')

    def __getattr__(self, name):
        """Fallback for any other attributes"""
        return self._dict.get(name)


class ResponseWrapper:
    """Wrapper to make dictionary response compatible with BetaMessage interface"""

    def __init__(self, response_dict: dict):
        self._dict = response_dict

    @property
    def content(self):
        """Provide .content attribute access for _response_to_params"""
        content_list = self._dict.get('content', [])
        # Wrap each content block to provide Pydantic model interface
        return [ContentBlockWrapper(block) for block in content_list]

    @property
    def stop_reason(self):
        """Provide .stop_reason attribute access"""
        return self._dict.get('stop_reason')

    def __getattr__(self, name):
        """Fallback for any other attributes"""
        return self._dict.get(name)


class RawResponse:
    """Wrapper to make LegacyUseClient compatible with Anthropic client interface"""

    def __init__(self, parsed_data: Any, http_response: httpx.Response):
        self.parsed_data = parsed_data
        self.http_response = http_response

    def parse(self):
        """Return wrapped response data that provides BetaMessage interface"""
        return ResponseWrapper(self.parsed_data)


class LegacyUseClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._beta = None

    @property
    def beta(self):
        if self._beta is None:
            self._beta = Beta(self)
        return self._beta


class Beta:
    def __init__(self, client: LegacyUseClient):
        self.client = client
        self._messages = None

    @property
    def messages(self):
        if self._messages is None:
            self._messages = Messages(self.client)
        return self._messages


class Messages:
    def __init__(self, client: LegacyUseClient):
        self.client = client
        self._with_raw_response = None

    @property
    def with_raw_response(self):
        if self._with_raw_response is None:
            self._with_raw_response = WithRawResponse(self.client)
        return self._with_raw_response


class WithRawResponse:
    def __init__(self, client: LegacyUseClient):
        self.client = client

    async def create(
        self,
        max_tokens: int,
        messages: list[BetaMessageParam],
        model: str,
        system: str | Iterable[BetaTextBlockParam],
        tools: list,
        betas: list[str],
        **kwargs,
    ) -> RawResponse:
        url = settings.LEGACYUSE_PROXY_BASE_URL + 'create'
        headers = {
            'x-api-key': self.client.api_key,
            'Content-Type': 'application/json',
        }
        data = {
            'max_tokens': max_tokens,
            'messages': messages,
            'model': model,
            'system': system,
            'tools': tools,
            'betas': betas,
            **kwargs,
        }

        logger.info(f'Sending request to {url} with headers: {headers}')

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, headers=headers, json=data)
            try:
                response_json = response.json()
                # Return wrapped response that's compatible with Anthropic client interface
                logger.info(f'Response status code: {response.status_code}')
                if response.status_code == 403:
                    raise APIStatusError(
                        message='API Credits Exceeded',
                        response=response,
                        body=response_json,
                    )
                if response.status_code != 200:
                    logger.error(f'Failed to execute API: {response_json}')
                    raise APIStatusError(
                        message=response_json['error'],
                        response=response,
                        body=response_json,
                    )
                return RawResponse(response_json, response)
            except Exception as e:
                logger.error(f'Failed to parse response JSON: {e}')
                raise
