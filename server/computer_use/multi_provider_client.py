"""
Simplified multi-provider client abstraction.
Supports Anthropic, OpenAI, and UI-TARS providers with minimal code.
"""

import json
from typing import Any, Dict, List, Optional

import httpx
import instructor
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock, AsyncAnthropicVertex
from anthropic.types.beta import BetaMessageParam
from openai import AsyncOpenAI

from server.computer_use.config import APIProvider
from server.computer_use.logging import logger


class MultiProviderClient:
    """Simplified multi-provider client"""
    
    def __init__(self, provider: APIProvider, api_key: str, **kwargs):
        self.provider = provider
        self.api_key = api_key
        
        if provider == APIProvider.ANTHROPIC:
            self.client = AsyncAnthropic(api_key=api_key, max_retries=4)
        elif provider == APIProvider.OPENAI:
            base_url = kwargs.get('base_url')
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        elif provider == APIProvider.UITARS:
            self.base_url = kwargs.get('base_url', 'https://api.uitars.com').rstrip('/')
            self.client = None  # HTTP-based
        elif provider == APIProvider.BEDROCK:
            # Keep existing Bedrock logic
            aws_region = kwargs.get('aws_region')
            bedrock_kwargs = {'aws_region': aws_region}
            if kwargs.get('aws_access_key') and kwargs.get('aws_secret_key'):
                bedrock_kwargs['aws_access_key'] = kwargs['aws_access_key']
                bedrock_kwargs['aws_secret_key'] = kwargs['aws_secret_key']
                if kwargs.get('aws_session_token'):
                    bedrock_kwargs['aws_session_token'] = kwargs['aws_session_token']
            self.client = AsyncAnthropicBedrock(**bedrock_kwargs)
        elif provider == APIProvider.VERTEX:
            self.client = AsyncAnthropicVertex()
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        # Create beta interface for compatibility
        self.beta = BetaInterface(self)
    
    async def _call_openai(self, messages, model, system, tools, max_tokens, temperature, **kwargs):
        """Call OpenAI API"""
        # Convert system to OpenAI format
        openai_messages = []
        if system:
            system_text = system[0].get('text', '') if system else ''
            if system_text:
                openai_messages.append({'role': 'system', 'content': system_text})
        
        # Convert messages
        for msg in messages:
            openai_msg = {'role': msg['role']}
            content = []
            for block in msg.get('content', []):
                if isinstance(block, dict):
                    if block.get('type') == 'text':
                        content.append(block.get('text', ''))
                    elif block.get('type') == 'tool_result':
                        content.append(block.get('content', ''))
            openai_msg['content'] = ' '.join(content) if content else ''
            openai_messages.append(openai_msg)
        
        # Convert tools
        openai_tools = None
        if tools:
            openai_tools = []
            for tool in tools:
                openai_tools.append({
                    'type': 'function',
                    'function': {
                        'name': tool['name'],
                        'description': tool.get('description', ''),
                        'parameters': tool.get('input_schema', {})
                    }
                })
        
        # Make API call
        params = {
            'model': model,
            'messages': openai_messages,
            'max_tokens': max_tokens,
            'temperature': temperature
        }
        if openai_tools:
            params['tools'] = openai_tools
        
        response = await self.client.chat.completions.create(**params)
        
        # Convert response back to Anthropic format
        choice = response.choices[0]
        content = []
        
        if choice.message.content:
            content.append({
                'type': 'text',
                'text': choice.message.content
            })
        
        if choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                content.append({
                    'type': 'tool_use',
                    'id': tool_call.id,
                    'name': tool_call.function.name,
                    'input': json.loads(tool_call.function.arguments)
                })
        
        # Map finish reason
        stop_reason_map = {
            'stop': 'end_turn',
            'length': 'max_tokens',
            'tool_calls': 'tool_use'
        }
        stop_reason = stop_reason_map.get(choice.finish_reason, choice.finish_reason)
        
        return MockResponse(content, stop_reason)
    
    async def _call_uitars(self, messages, model, system, tools, max_tokens, temperature, **kwargs):
        """Call UI-TARS API"""
        # Convert to UI-TARS format (similar to OpenAI)
        uitars_messages = []
        if system:
            system_text = system[0].get('text', '') if system else ''
            if system_text:
                uitars_messages.append({'role': 'system', 'content': system_text})
        
        for msg in messages:
            uitars_msg = {'role': msg['role']}
            content = []
            for block in msg.get('content', []):
                if isinstance(block, dict) and block.get('type') == 'text':
                    content.append(block.get('text', ''))
            uitars_msg['content'] = ' '.join(content) if content else ''
            uitars_messages.append(uitars_msg)
        
        # Convert tools
        uitars_tools = []
        if tools:
            for tool in tools:
                uitars_tools.append({
                    'type': 'function',
                    'function': {
                        'name': tool['name'],
                        'description': tool.get('description', ''),
                        'parameters': tool.get('input_schema', {})
                    }
                })
        
        # Make HTTP request
        payload = {
            'model': model,
            'messages': uitars_messages,
            'max_tokens': max_tokens,
            'temperature': temperature
        }
        if uitars_tools:
            payload['tools'] = uitars_tools
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f'{self.base_url}/v1/chat/completions',
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
        
        # Convert response
        choice = data['choices'][0]
        content = []
        
        if choice['message'].get('content'):
            content.append({
                'type': 'text',
                'text': choice['message']['content']
            })
        
        if choice['message'].get('tool_calls'):
            for tool_call in choice['message']['tool_calls']:
                content.append({
                    'type': 'tool_use',
                    'id': tool_call['id'],
                    'name': tool_call['function']['name'],
                    'input': json.loads(tool_call['function']['arguments'])
                })
        
        stop_reason_map = {
            'stop': 'end_turn',
            'length': 'max_tokens',
            'tool_calls': 'tool_use'
        }
        stop_reason = stop_reason_map.get(choice['finish_reason'], choice['finish_reason'])
        
        return MockResponse(content, stop_reason)


class BetaInterface:
    """Compatibility interface for existing sampling loop"""
    
    def __init__(self, client: MultiProviderClient):
        self.client = client
        self.messages = MessagesInterface(client)


class MessagesInterface:
    """Messages interface"""
    
    def __init__(self, client: MultiProviderClient):
        self.client = client
        self.with_raw_response = WithRawResponseInterface(client)


class WithRawResponseInterface:
    """With raw response interface"""
    
    def __init__(self, client: MultiProviderClient):
        self.client = client
    
    async def create(self, messages, model, system, tools, max_tokens=4096, temperature=0.0, betas=None, **kwargs):
        """Create message with any provider"""
        
        if self.client.provider in [APIProvider.ANTHROPIC, APIProvider.BEDROCK, APIProvider.VERTEX]:
            # Use original Anthropic client
            raw_response = await self.client.client.beta.messages.with_raw_response.create(
                messages=messages,
                model=model,
                system=system,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                betas=betas or [],
                **kwargs
            )
            return raw_response
        
        elif self.client.provider == APIProvider.OPENAI:
            response = await self.client._call_openai(messages, model, system, tools, max_tokens, temperature, **kwargs)
            return MockRawResponse(response)
        
        elif self.client.provider == APIProvider.UITARS:
            response = await self.client._call_uitars(messages, model, system, tools, max_tokens, temperature, **kwargs)
            return MockRawResponse(response)
        
        else:
            raise ValueError(f"Unsupported provider: {self.client.provider}")


class MockResponse:
    """Mock response for non-Anthropic providers"""
    
    def __init__(self, content, stop_reason):
        self.content = [MockContentBlock(block) for block in content]
        self.stop_reason = stop_reason


class MockContentBlock:
    """Mock content block"""
    
    def __init__(self, data):
        self._data = data
    
    def model_dump(self):
        return self._data
    
    @property
    def type(self):
        return self._data.get('type')
    
    @property
    def text(self):
        return self._data.get('text')
    
    @property
    def name(self):
        return self._data.get('name')
    
    @property
    def id(self):
        return self._data.get('id')
    
    @property
    def input(self):
        return self._data.get('input')
    
    def __getitem__(self, key):
        return self._data[key]


class MockRawResponse:
    """Mock raw response for compatibility"""
    
    def __init__(self, response):
        self._response = response
        self.http_response = MockHttpResponse()
    
    def parse(self):
        return self._response


class MockHttpResponse:
    """Mock HTTP response"""
    
    def __init__(self):
        self.request = MockRequest()
        self.status_code = 200


class MockRequest:
    """Mock request"""
    pass