"""
Simplified tests for multi-provider sampling loop functionality.
Tests Anthropic, OpenAI, and UI-TARS providers with mocked requests.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from typing import Any, Dict, List

from anthropic.types.beta import BetaMessageParam, BetaTextBlockParam

from server.computer_use.config import APIProvider
from server.computer_use.tools import ToolResult


class MockDatabaseService:
    """Mock database service for testing"""
    
    def __init__(self):
        self.messages = []
        self.sequence_counter = 1
    
    def get_next_message_sequence(self, job_id):
        return self.sequence_counter
    
    def add_job_message(self, job_id, sequence, role, content):
        self.messages.append({
            'job_id': job_id,
            'sequence': sequence,
            'role': role,
            'content': content
        })
        self.sequence_counter += 1
    
    def get_job_messages(self, job_id):
        return [msg for msg in self.messages if msg['job_id'] == job_id]
    
    def get_session(self, session_id):
        return {'container_ip': '127.0.0.1'}


class MockToolCollection:
    """Mock tool collection for testing"""
    
    def to_params(self):
        return [
            {
                'name': 'computer',
                'description': 'Use computer to perform actions',
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        'action': {'type': 'string'},
                        'coordinate': {'type': 'array'}
                    }
                }
            }
        ]
    
    async def run(self, name: str, tool_input: Dict[str, Any], session_id: str = None):
        """Mock tool execution"""
        if name == 'computer':
            return ToolResult(
                output=f"Executed {tool_input.get('action', 'unknown')} action",
                error=None,
                base64_image="mock_screenshot_data"
            )
        elif name == 'extraction':
            return ToolResult(
                output='{"result": {"extracted_data": "test_value"}}',
                error=None,
                base64_image=None
            )
        else:
            return ToolResult(
                output=f"Mock result for {name}",
                error=None,
                base64_image=None
            )


@pytest.fixture
def mock_db():
    return MockDatabaseService()


@pytest.fixture
def mock_tool_collection():
    return MockToolCollection()


@pytest.fixture
def job_id():
    return uuid4()


@pytest.fixture
def sample_messages():
    return [
        BetaMessageParam(
            role='user',
            content=[BetaTextBlockParam(type='text', text='Take a screenshot')]
        )
    ]


class TestMultiProviderClient:
    """Test simplified multi-provider client"""
    
    def test_client_creation(self):
        """Test that multi-provider client creates correctly"""
        from server.computer_use.multi_provider_client import MultiProviderClient
        
        # Test Anthropic client creation
        anthropic_client = MultiProviderClient(APIProvider.ANTHROPIC, 'test-key')
        assert anthropic_client.provider == APIProvider.ANTHROPIC
        
        # Test OpenAI client creation
        openai_client = MultiProviderClient(APIProvider.OPENAI, 'test-key')
        assert openai_client.provider == APIProvider.OPENAI
        
        # Test UI-TARS client creation
        uitars_client = MultiProviderClient(APIProvider.UITARS, 'test-key', base_url='https://test.uitars.com')
        assert uitars_client.provider == APIProvider.UITARS
    
    @pytest.mark.asyncio
    async def test_openai_provider(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test OpenAI provider with mocked responses"""
        
        with patch('server.computer_use.multi_provider_client.AsyncOpenAI') as mock_openai_class:
            mock_openai_client = AsyncMock()
            
            # Mock completion response
            mock_completion = Mock()
            mock_completion.choices = [Mock(
                message=Mock(
                    content=None,
                    tool_calls=[Mock(
                        id='tool_123',
                        function=Mock(
                            name='extraction',
                            arguments='{"data": "test_result"}'
                        )
                    )]
                ),
                finish_reason='tool_calls'
            )]
            
            mock_openai_client.chat.completions.create.return_value = mock_completion
            mock_openai_class.return_value = mock_openai_client
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': True, 'reason': 'OK'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    result, exchanges = await sampling_loop(
                        job_id=job_id,
                        db=mock_db,
                        model='gpt-4o',
                        provider=APIProvider.OPENAI,
                        system_prompt_suffix='',
                        messages=sample_messages,
                        output_callback=output_callback,
                        tool_output_callback=tool_output_callback,
                        max_tokens=1000,
                        tool_version='computer_use_20241022',
                        api_key='test-key',
                        session_id=str(uuid4())
                    )
                    
                    # Verify the result contains extracted data
                    assert result == {"extracted_data": "test_value"}
                    assert len(exchanges) >= 1
    
    @pytest.mark.asyncio
    async def test_uitars_provider(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test UI-TARS provider with mocked responses"""
        
        # Mock UI-TARS HTTP response
        mock_response_data = {
            'choices': [
                {
                    'message': {
                        'content': None,
                        'tool_calls': [
                            {
                                'id': 'tool_456',
                                'function': {
                                    'name': 'extraction',
                                    'arguments': '{"data": "test_result"}'
                                }
                            }
                        ]
                    },
                    'finish_reason': 'tool_calls'
                }
            ]
        }
        
        with patch('httpx.AsyncClient') as mock_httpx_class:
            mock_client = AsyncMock()
            mock_httpx_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_client.post.return_value = mock_response
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': True, 'reason': 'OK'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    result, exchanges = await sampling_loop(
                        job_id=job_id,
                        db=mock_db,
                        model='uitars-1.5',
                        provider=APIProvider.UITARS,
                        system_prompt_suffix='',
                        messages=sample_messages,
                        output_callback=output_callback,
                        tool_output_callback=tool_output_callback,
                        max_tokens=1000,
                        tool_version='computer_use_20241022',
                        api_key='test-key',
                        session_id=str(uuid4())
                    )
                    
                    # Verify the result contains extracted data
                    assert result == {"extracted_data": "test_value"}
                    assert len(exchanges) >= 1


class TestErrorHandling:
    """Test error handling across providers"""
    
    @pytest.mark.asyncio
    async def test_openai_api_error(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test OpenAI API error handling"""
        
        with patch('server.computer_use.multi_provider_client.AsyncOpenAI') as mock_openai_class:
            mock_openai_client = AsyncMock()
            mock_openai_client.chat.completions.create.side_effect = Exception("OpenAI API Error")
            mock_openai_class.return_value = mock_openai_client
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': True, 'reason': 'OK'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    with pytest.raises(Exception, match="OpenAI API Error"):
                        await sampling_loop(
                            job_id=job_id,
                            db=mock_db,
                            model='gpt-4o',
                            provider=APIProvider.OPENAI,
                            system_prompt_suffix='',
                            messages=sample_messages,
                            output_callback=output_callback,
                            tool_output_callback=tool_output_callback,
                            max_tokens=1000,
                            tool_version='computer_use_20241022',
                            api_key='test-key',
                            session_id=str(uuid4())
                        )


if __name__ == '__main__':
    pytest.main([__file__])