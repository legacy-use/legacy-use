"""
Multi-provider client abstraction using instructor library.
Supports Anthropic, OpenAI, and UI-TARS 1.5 providers.
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, Callable
from enum import StrEnum

import httpx
import instructor
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock, AsyncAnthropicVertex
from anthropic.types.beta import BetaMessageParam, BetaContentBlockParam
from openai import AsyncOpenAI
from pydantic import BaseModel

from server.computer_use.config import APIProvider
from server.computer_use.logging import logger


class ProviderResponse(BaseModel):
    """Standardized response format across all providers"""
    content: List[Dict[str, Any]]
    stop_reason: str
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Any] = None


class ProviderClient(ABC):
    """Abstract base class for all provider clients"""
    
    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        self.kwargs = kwargs
    
    @abstractmethod
    async def create_message(
        self,
        messages: List[BetaMessageParam],
        model: str,
        system: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ) -> ProviderResponse:
        """Create a message using the provider's API"""
        pass
    
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming responses"""
        pass


class AnthropicProviderClient(ProviderClient):
    """Anthropic provider client using instructor"""
    
    def __init__(self, api_key: str, provider_type: APIProvider = APIProvider.ANTHROPIC, **kwargs):
        super().__init__(api_key, **kwargs)
        self.provider_type = provider_type
        
        # Initialize the appropriate Anthropic client
        if provider_type == APIProvider.ANTHROPIC:
            self.client = AsyncAnthropic(api_key=api_key, max_retries=4)
        elif provider_type == APIProvider.BEDROCK:
            aws_region = kwargs.get('aws_region')
            aws_access_key = kwargs.get('aws_access_key')
            aws_secret_key = kwargs.get('aws_secret_key')
            aws_session_token = kwargs.get('aws_session_token')
            
            bedrock_kwargs = {'aws_region': aws_region}
            if aws_access_key and aws_secret_key:
                bedrock_kwargs['aws_access_key'] = aws_access_key
                bedrock_kwargs['aws_secret_key'] = aws_secret_key
                if aws_session_token:
                    bedrock_kwargs['aws_session_token'] = aws_session_token
            
            self.client = AsyncAnthropicBedrock(**bedrock_kwargs)
        elif provider_type == APIProvider.VERTEX:
            self.client = AsyncAnthropicVertex()
        else:
            raise ValueError(f"Unsupported Anthropic provider type: {provider_type}")
        
        # Wrap with instructor for structured outputs if needed
        self.instructor_client = instructor.from_anthropic(self.client)
    
    async def create_message(
        self,
        messages: List[BetaMessageParam],
        model: str,
        system: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        betas: Optional[List[str]] = None,
        **kwargs
    ) -> ProviderResponse:
        """Create a message using Anthropic's API"""
        
        try:
            # Use the original client for tool-based interactions
            raw_response = await self.client.beta.messages.with_raw_response.create(
                max_tokens=max_tokens,
                messages=messages,
                model=model,
                system=system,
                tools=tools,
                betas=betas or [],
                temperature=temperature,
                **kwargs
            )
            
            response = raw_response.parse()
            
            # Convert to standardized format
            content = []
            for block in response.content:
                if hasattr(block, 'model_dump'):
                    content.append(block.model_dump())
                else:
                    # Fallback for older format
                    content.append({
                        'type': getattr(block, 'type', 'text'),
                        'text': getattr(block, 'text', ''),
                        'name': getattr(block, 'name', None),
                        'id': getattr(block, 'id', None),
                        'input': getattr(block, 'input', None)
                    })
            
            usage = None
            if hasattr(response, 'usage'):
                usage = {
                    'input_tokens': response.usage.input_tokens,
                    'output_tokens': response.usage.output_tokens
                }
            
            return ProviderResponse(
                content=content,
                stop_reason=response.stop_reason,
                usage=usage,
                raw_response=raw_response
            )
            
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            raise
    
    def supports_streaming(self) -> bool:
        return True


class OpenAIProviderClient(ProviderClient):
    """OpenAI provider client using instructor"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        
        # Initialize OpenAI client
        client_kwargs = {'api_key': api_key}
        if base_url:
            client_kwargs['base_url'] = base_url
        
        self.client = AsyncOpenAI(**client_kwargs)
        
        # Wrap with instructor for structured outputs
        self.instructor_client = instructor.from_openai(self.client)
    
    async def create_message(
        self,
        messages: List[BetaMessageParam],
        model: str,
        system: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ) -> ProviderResponse:
        """Create a message using OpenAI's API"""
        
        try:
            # Convert messages to OpenAI format
            openai_messages = self._convert_messages_to_openai(messages, system)
            
            # Convert tools to OpenAI format
            openai_tools = self._convert_tools_to_openai(tools) if tools else None
            
            # Make the API call
            completion_kwargs = {
                'model': model,
                'messages': openai_messages,
                'max_tokens': max_tokens,
                'temperature': temperature,
                **kwargs
            }
            
            if openai_tools:
                completion_kwargs['tools'] = openai_tools
                completion_kwargs['tool_choice'] = 'auto'
            
            response = await self.client.chat.completions.create(**completion_kwargs)
            
            # Convert response to standardized format
            content = []
            choice = response.choices[0]
            message = choice.message
            
            if message.content:
                content.append({
                    'type': 'text',
                    'text': message.content
                })
            
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    content.append({
                        'type': 'tool_use',
                        'id': tool_call.id,
                        'name': tool_call.function.name,
                        'input': json.loads(tool_call.function.arguments)
                    })
            
            # Map OpenAI finish reasons to Anthropic-like stop reasons
            stop_reason_mapping = {
                'stop': 'end_turn',
                'length': 'max_tokens',
                'tool_calls': 'tool_use',
                'content_filter': 'stop_sequence',
                'function_call': 'tool_use'  # Legacy
            }
            
            stop_reason = stop_reason_mapping.get(choice.finish_reason, choice.finish_reason)
            
            usage = None
            if response.usage:
                usage = {
                    'input_tokens': response.usage.prompt_tokens,
                    'output_tokens': response.usage.completion_tokens
                }
            
            return ProviderResponse(
                content=content,
                stop_reason=stop_reason,
                usage=usage,
                raw_response=response
            )
            
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise
    
    def _convert_messages_to_openai(
        self, 
        messages: List[BetaMessageParam], 
        system: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert Anthropic-style messages to OpenAI format"""
        
        openai_messages = []
        
        # Add system message if provided
        if system:
            system_text = ""
            for sys_block in system:
                if sys_block.get('type') == 'text':
                    system_text += sys_block.get('text', '')
            
            if system_text:
                openai_messages.append({
                    'role': 'system',
                    'content': system_text
                })
        
        # Convert regular messages
        for message in messages:
            openai_message = {
                'role': message['role']
            }
            
            content_parts = []
            for content_block in message.get('content', []):
                if isinstance(content_block, dict):
                    if content_block.get('type') == 'text':
                        content_parts.append(content_block.get('text', ''))
                    elif content_block.get('type') == 'image':
                        # Handle image content
                        content_parts.append({
                            'type': 'image_url',
                            'image_url': {
                                'url': f"data:image/png;base64,{content_block.get('source', {}).get('data', '')}"
                            }
                        })
                    elif content_block.get('type') == 'tool_result':
                        # Convert tool result to assistant message
                        if content_block.get('content'):
                            content_parts.append(content_block['content'])
                else:
                    # Handle string content
                    content_parts.append(str(content_block))
            
            if len(content_parts) == 1 and isinstance(content_parts[0], str):
                openai_message['content'] = content_parts[0]
            else:
                openai_message['content'] = content_parts
            
            openai_messages.append(openai_message)
        
        return openai_messages
    
    def _convert_tools_to_openai(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert Anthropic-style tools to OpenAI format"""
        
        openai_tools = []
        for tool in tools:
            openai_tool = {
                'type': 'function',
                'function': {
                    'name': tool['name'],
                    'description': tool.get('description', ''),
                    'parameters': tool.get('input_schema', {})
                }
            }
            openai_tools.append(openai_tool)
        
        return openai_tools
    
    def supports_streaming(self) -> bool:
        return True


class UITarsProviderClient(ProviderClient):
    """UI-TARS 1.5 provider client"""
    
    def __init__(self, api_key: str, base_url: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = base_url.rstrip('/')
    
    async def create_message(
        self,
        messages: List[BetaMessageParam],
        model: str,
        system: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ) -> ProviderResponse:
        """Create a message using UI-TARS API"""
        
        try:
            # Convert to UI-TARS format
            uitars_payload = {
                'model': model,
                'messages': self._convert_messages_to_uitars(messages, system),
                'tools': self._convert_tools_to_uitars(tools) if tools else [],
                'max_tokens': max_tokens,
                'temperature': temperature,
                **kwargs
            }
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f'{self.base_url}/v1/chat/completions',
                    headers=headers,
                    json=uitars_payload
                )
                response.raise_for_status()
                response_data = response.json()
            
            # Convert response to standardized format
            content = []
            
            if 'choices' in response_data and response_data['choices']:
                choice = response_data['choices'][0]
                message = choice.get('message', {})
                
                if message.get('content'):
                    content.append({
                        'type': 'text',
                        'text': message['content']
                    })
                
                if message.get('tool_calls'):
                    for tool_call in message['tool_calls']:
                        content.append({
                            'type': 'tool_use',
                            'id': tool_call.get('id', ''),
                            'name': tool_call.get('function', {}).get('name', ''),
                            'input': json.loads(tool_call.get('function', {}).get('arguments', '{}'))
                        })
                
                # Map finish reason
                finish_reason = choice.get('finish_reason', 'stop')
                stop_reason_mapping = {
                    'stop': 'end_turn',
                    'length': 'max_tokens',
                    'tool_calls': 'tool_use',
                    'content_filter': 'stop_sequence'
                }
                stop_reason = stop_reason_mapping.get(finish_reason, finish_reason)
            else:
                stop_reason = 'end_turn'
            
            usage = None
            if 'usage' in response_data:
                usage = {
                    'input_tokens': response_data['usage'].get('prompt_tokens', 0),
                    'output_tokens': response_data['usage'].get('completion_tokens', 0)
                }
            
            return ProviderResponse(
                content=content,
                stop_reason=stop_reason,
                usage=usage,
                raw_response=response_data
            )
            
        except Exception as e:
            logger.error(f"UI-TARS API call failed: {e}")
            raise
    
    def _convert_messages_to_uitars(
        self, 
        messages: List[BetaMessageParam], 
        system: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert messages to UI-TARS format (similar to OpenAI)"""
        
        uitars_messages = []
        
        # Add system message
        if system:
            system_text = ""
            for sys_block in system:
                if sys_block.get('type') == 'text':
                    system_text += sys_block.get('text', '')
            
            if system_text:
                uitars_messages.append({
                    'role': 'system',
                    'content': system_text
                })
        
        # Convert regular messages (similar to OpenAI conversion)
        for message in messages:
            uitars_message = {
                'role': message['role']
            }
            
            content_parts = []
            for content_block in message.get('content', []):
                if isinstance(content_block, dict):
                    if content_block.get('type') == 'text':
                        content_parts.append(content_block.get('text', ''))
                    elif content_block.get('type') == 'image':
                        # UI-TARS supports images
                        content_parts.append({
                            'type': 'image_url',
                            'image_url': {
                                'url': f"data:image/png;base64,{content_block.get('source', {}).get('data', '')}"
                            }
                        })
                else:
                    content_parts.append(str(content_block))
            
            if len(content_parts) == 1 and isinstance(content_parts[0], str):
                uitars_message['content'] = content_parts[0]
            else:
                uitars_message['content'] = content_parts
            
            uitars_messages.append(uitars_message)
        
        return uitars_messages
    
    def _convert_tools_to_uitars(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools to UI-TARS format (similar to OpenAI)"""
        
        uitars_tools = []
        for tool in tools:
            uitars_tool = {
                'type': 'function',
                'function': {
                    'name': tool['name'],
                    'description': tool.get('description', ''),
                    'parameters': tool.get('input_schema', {})
                }
            }
            uitars_tools.append(uitars_tool)
        
        return uitars_tools
    
    def supports_streaming(self) -> bool:
        return True


class MultiProviderClientFactory:
    """Factory for creating provider clients"""
    
    @staticmethod
    def create_client(
        provider: APIProvider,
        api_key: str,
        **kwargs
    ) -> ProviderClient:
        """Create a provider client based on the provider type"""
        
        if provider in [APIProvider.ANTHROPIC, APIProvider.BEDROCK, APIProvider.VERTEX]:
            return AnthropicProviderClient(api_key, provider, **kwargs)
        elif provider == APIProvider.OPENAI:
            return OpenAIProviderClient(api_key, **kwargs)
        elif provider == APIProvider.UITARS:
            base_url = kwargs.get('base_url', 'https://api.uitars.com')
            return UITarsProviderClient(api_key, base_url, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {provider}")


class MultiProviderWrapper:
    """Wrapper that provides a unified interface for all providers"""
    
    def __init__(self, provider_client: ProviderClient):
        self.provider_client = provider_client
        
        # Create a mock beta.messages.with_raw_response interface for compatibility
        self.beta = MockBeta(self)
    
    async def create_message(self, **kwargs) -> ProviderResponse:
        """Create a message using the underlying provider"""
        return await self.provider_client.create_message(**kwargs)


class MockBeta:
    """Mock beta interface for compatibility with existing code"""
    
    def __init__(self, wrapper: MultiProviderWrapper):
        self.wrapper = wrapper
        self.messages = MockMessages(wrapper)


class MockMessages:
    """Mock messages interface for compatibility"""
    
    def __init__(self, wrapper: MultiProviderWrapper):
        self.wrapper = wrapper
        self.with_raw_response = MockWithRawResponse(wrapper)


class MockWithRawResponse:
    """Mock with_raw_response interface for compatibility"""
    
    def __init__(self, wrapper: MultiProviderWrapper):
        self.wrapper = wrapper
    
    async def create(self, **kwargs) -> 'MockRawResponse':
        """Create a message and return a mock raw response"""
        response = await self.wrapper.create_message(**kwargs)
        return MockRawResponse(response)


class MockRawResponse:
    """Mock raw response for compatibility with existing parsing code"""
    
    def __init__(self, provider_response: ProviderResponse):
        self.provider_response = provider_response
        self.http_response = MockHttpResponse(provider_response.raw_response)
    
    def parse(self) -> 'MockParsedResponse':
        """Parse the response"""
        return MockParsedResponse(self.provider_response)


class MockHttpResponse:
    """Mock HTTP response for compatibility"""
    
    def __init__(self, raw_response: Any):
        self.request = MockRequest()
        self.status_code = 200
        self.raw_response = raw_response


class MockRequest:
    """Mock request for compatibility"""
    pass


class MockParsedResponse:
    """Mock parsed response that matches Anthropic's response interface"""
    
    def __init__(self, provider_response: ProviderResponse):
        self.provider_response = provider_response
        self._content = [MockContentBlock(block) for block in provider_response.content]
        self.stop_reason = provider_response.stop_reason
        self.usage = provider_response.usage
    
    @property
    def content(self):
        return self._content


class MockContentBlock:
    """Mock content block that provides both dict and attribute access"""
    
    def __init__(self, block_data: Dict[str, Any]):
        self._data = block_data
    
    def model_dump(self) -> Dict[str, Any]:
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
    
    def get(self, key, default=None):
        return self._data.get(key, default)